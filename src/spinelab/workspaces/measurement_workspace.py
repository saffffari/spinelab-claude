from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QStyle,
    QStyleOptionViewItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from spinelab.exports import export_measurement_bundle, write_measurements_pdf
from spinelab.io import CaseStore
from spinelab.segmentation.anatomy_groups import available_anatomy_groups
from spinelab.ui.widgets.anatomy_tree import AnatomyExplorerTree
from spinelab.models import CaseManifest, MetricRecord, VolumeMetadata
from spinelab.pipeline.artifacts import read_json_artifact
from spinelab.segmentation import summary_for_active_bundle, summary_for_manifest
from spinelab.services import RenderBackendProbe, SettingsService
from spinelab.ui.svg_icons import build_svg_icon, build_svg_pixmap
from spinelab.ui.theme import (
    GEOMETRY,
    TEXT_STYLES,
    THEME_COLORS,
    qcolor_from_css,
)
from spinelab.ui.widgets import (
    CapsuleButton,
    NestedBubbleFrame,
    PanelFrame,
    TransparentSplitter,
    apply_text_role,
    major_button_icon_size,
    schedule_splitter_midpoint,
)
from spinelab.visualization import OrthographicMeshViewport, SpineViewport3D
from spinelab.visualization.measurement_overlays import (
    MeasurementOverlayController,
    OverlayGeometry,
)
from spinelab.visualization.viewer_3d import (
    DEMO_VERTEBRAE,
    DETAIL_PRESET_LEVELS,
    VERTEBRA_INDEX,
    VIEWPORT_MODE_ICON_PATHS,
    MockVertebra,
    ViewportMode,
    apply_group_transform,
    build_mesh_spec_from_path,
    build_mesh_specs_from_glb_path,
    build_pelvis_world_transform,
    detail_preset_level,
)
from spinelab.workspaces.base import WorkspacePage

TARGET_MEASUREMENT_ORDER = (
    "Cobb Angle",
    "Thoracic Kyphosis",
    "Lumbar Lordosis",
    "Pelvic Tilt",
    "Sagittal Vertical Axis",
)
TARGET_MEASUREMENT_METADATA = {
    "Cobb Angle": ("cobb_angle", "deg"),
    "Thoracic Kyphosis": ("thoracic_kyphosis", "deg"),
    "Lumbar Lordosis": ("lumbar_lordosis", "deg"),
    "Pelvic Tilt": ("pelvic_tilt", "deg"),
    "Sagittal Vertical Axis": ("sagittal_vertical_axis", "mm"),
}

DEFAULT_SELECTION_ID = DEMO_VERTEBRAE[2].vertebra_id
SAVE_ICON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-save-32.svg"
PENDING_ANALYSIS_ICON_PATH = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-document-add-danger-16.svg"
)
MANUAL_TOOL_ICON_PATHS = {
    "select": Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-cursor-filled-32.svg",
    "distance": Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-line-flow-diagonal-up-right-filled-32.svg",
    "angle": Path(__file__).resolve().parents[1]
    / "ui"
    / "assets"
    / "fluent-angle-32.svg",
}


@dataclass(frozen=True)
class VertebraSelectionState:
    selected_ids: tuple[str, ...]
    active_id: str | None
    reference_id: str | None
    isolate_selection: bool = False


@dataclass(frozen=True)
class RelativeMotionMetrics:
    active_id: str
    reference_id: str
    delta_x: float
    delta_y: float
    delta_z: float
    distance: float


class MeasurementSelectionButton(QToolButton):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MeasurementCheckButton")
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(GEOMETRY.control_height_sm - 8, GEOMETRY.control_height_sm - 8)
        apply_text_role(self, "micro")
        self.setText("")
        self.toggled.connect(lambda _checked: self.update())

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer_inset = 1
        ring_rect = self.rect().adjusted(outer_inset, outer_inset, -outer_inset, -outer_inset)
        ring_color = (
            qcolor_from_css(THEME_COLORS.focus)
            if self.isChecked() or self.underMouse()
            else qcolor_from_css(THEME_COLORS.text_muted)
        )
        painter.setPen(ring_color)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)
        if not self.isChecked():
            painter.end()
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor_from_css(THEME_COLORS.focus))
        inset = max(3, min(self.width(), self.height()) // 4)
        indicator_rect = self.rect().adjusted(inset, inset, -inset, -inset)
        painter.drawEllipse(indicator_rect)
        painter.end()


class MeasurementTree(QTreeWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MeasurementTree")
        self.setHeaderHidden(True)
        self.setIndentation(GEOMETRY.unit * 2)
        self.setRootIsDecorated(True)
        self.setAllColumnsShowFocus(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformRowHeights(True)

    def _selection_fill_rect(self, row_rect: QRect) -> QRect:
        vertical_inset = max(1, GEOMETRY.unit // 2)
        return QRect(
            0,
            row_rect.top() + vertical_inset,
            max(0, self.viewport().width()),
            max(0, row_rect.height() - (vertical_inset * 2)),
        )

    def drawRow(self, painter: QPainter, options: QStyleOptionViewItem, index) -> None:
        option = QStyleOptionViewItem(options)
        option.showDecorationSelected = False
        selection_model = self.selectionModel()
        is_selected = selection_model.isSelected(index) if selection_model is not None else False
        if is_selected:
            selection_rect = self._selection_fill_rect(option.rect)
            if not selection_rect.isEmpty():
                painter.save()
                painter.setClipRect(self.viewport().rect())
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qcolor_from_css(THEME_COLORS.focus_soft))
                radius = selection_rect.height() / 2.0
                painter.drawRoundedRect(selection_rect, radius, radius)
                painter.restore()
            option.state &= ~QStyle.StateFlag.State_Selected
            option.state &= ~QStyle.StateFlag.State_HasFocus
        super().drawRow(painter, option, index)


class VertebraSelectionButton(CapsuleButton):
    interaction_requested = Signal(str, bool, bool)

    def __init__(self, vertebra_id: str) -> None:
        super().__init__(vertebra_id)
        self._vertebra_id = vertebra_id
        self.setObjectName("VertebraSelectionButton")
        self.setProperty("selectionState", "idle")
        self.setFixedHeight(max(20, GEOMETRY.control_height_sm - 12))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_text_role(self, "micro")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            remove_requested = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.interaction_requested.emit(
                self._vertebra_id,
                remove_requested,
                False,
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def set_selection_state(self, selection_state: str) -> None:
        self.setProperty("selectionState", selection_state)
        refresh_widget_style(self)


class ManualMeasurementToolButton(QToolButton):
    tool_selected = Signal(str)

    def __init__(self, tool_id: str, tooltip: str) -> None:
        super().__init__()
        self._tool_id = tool_id
        self.setObjectName("ManualMeasurementToolButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFixedSize(GEOMETRY.toolbar_control_size, GEOMETRY.toolbar_control_size)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.clicked.connect(lambda checked=False: self.tool_selected.emit(self._tool_id))

    @property
    def tool_id(self) -> str:
        return self._tool_id


class MeasurementSummaryCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("InspectorSummaryCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        kicker = QLabel(title.upper())
        kicker.setObjectName("InspectorSummaryKicker")
        apply_text_role(kicker, "micro")
        layout.addWidget(kicker)

        self.value_label = QLabel("")
        apply_text_role(self.value_label, "body-emphasis")
        layout.addWidget(self.value_label)


class MeasurementWorkspace(WorkspacePage):
    def __init__(
        self,
        manifest: CaseManifest,
        settings: SettingsService,
        *,
        store: CaseStore | None = None,
        render_backend: RenderBackendProbe | None = None,
        interactive_3d_enabled: bool = True,
        analysis_ready: bool = True,
        initial_viewport_mode: ViewportMode = ViewportMode.SOLID,
        initial_detail_level: int = 2,
        initial_point_size: int = 8,
        initial_baseline_pose_visible: bool = True,
        initial_standing_pose_visible: bool = True,
        initial_selected_ids: tuple[str, ...] = (),
        initial_active_id: str | None = None,
        initial_reference_id: str | None = None,
        initial_isolate_selection: bool = False,
        on_display_state_changed: (
            Callable[[ViewportMode, int, int, bool, bool], None] | None
        ) = None,
        on_selection_state_changed: (
            Callable[[tuple[str, ...], str | None, str | None, bool], None] | None
        ) = None,
    ) -> None:
        self._manifest = manifest
        self._workspace_settings = settings
        self._store = store or CaseStore()
        self._render_backend = render_backend
        self._analysis_ready = analysis_ready
        self._interactive_3d_enabled = interactive_3d_enabled
        self._initial_viewport_mode = initial_viewport_mode
        self._initial_detail_level = initial_detail_level
        self._initial_point_size = initial_point_size
        self._initial_baseline_pose_visible = initial_baseline_pose_visible
        self._initial_standing_pose_visible = initial_standing_pose_visible
        self._initial_selected_ids = initial_selected_ids
        self._initial_active_id = initial_active_id
        self._initial_reference_id = initial_reference_id
        self._initial_isolate_selection = initial_isolate_selection
        self._on_display_state_changed = on_display_state_changed
        self._on_selection_state_changed = on_selection_state_changed
        self._shared_state_callbacks_enabled = False
        self._synchronizing_shared_state = False
        self._scene_models = models_for_manifest(manifest) if self._analysis_ready else []
        self._selection_index = build_selection_model_index(
            self._scene_models,
            pose_name="baseline",
        ) or build_selection_model_index(
            self._scene_models,
            pose_name="standing",
        )
        self._baseline_index = build_selection_model_index(
            self._scene_models,
            pose_name="baseline",
            include_nonselectable=True,
        )
        self._standing_index = build_selection_model_index(
            self._scene_models,
            pose_name="standing",
            include_nonselectable=True,
        )
        self._model_index = self._baseline_index or self._standing_index
        self._has_model_scene = bool(self._scene_models)
        self._has_comparison_scene = bool(self._standing_index)
        self._model_ids = list(self._selection_index)
        self._reference_ids = tuple(self._model_index)
        self._default_reference_id = default_primary_id_for_lookup(
            self._reference_ids,
            has_model_scene=self._has_model_scene,
        )
        self._selection_state = build_initial_selection_state(
            self._model_ids,
            self._has_model_scene,
            reference_ids=self._reference_ids,
        )
        self._measurement_values = (
            measurement_values_for_manifest(manifest) if self._analysis_ready else {}
        )
        self._measurement_records = (
            measurement_records_for_manifest(manifest) if self._analysis_ready else ()
        )
        self._measurement_record_lookup = {
            measurement_record_label(record): record for record in self._measurement_records
        }
        self._selected_measurement = next(iter(self._measurement_values), "")
        self._manual_tool = "select"
        self._manual_measurement_points: list[tuple[float, float, float]] = []
        self._overlay_status_label = QLabel("")
        self._overlay_status_label.setWordWrap(True)
        apply_text_role(self._overlay_status_label, "meta")
        self._baseline_pose_visible = True
        self._standing_pose_visible = False
        self._viewport: SpineViewport3D

        self._anatomy_tree = AnatomyExplorerTree()
        self._measurement_tree = MeasurementTree()
        self._measurement_tree.setColumnCount(3)
        self._measurement_tree.setEnabled(self._analysis_ready)

        self._selected_summary = MeasurementSummaryCard("Measurements")
        self._vertebra_summary = MeasurementSummaryCard("Vertebrae")
        self._save_measurements_button = CapsuleButton(
            "Save Measurements",
            variant="primary",
            major=True,
        )
        self._export_model_button = CapsuleButton(
            "Export Model",
            variant="info",
            major=True,
        )
        self._isolate_button = CapsuleButton("Isolate Selection", checkable=True)
        self._clear_selection_button = CapsuleButton("Clear Selection")
        self._set_reference_frame_button = CapsuleButton("Set Reference Frame")
        self._export_status_label = QLabel(
            "Analyze required." if not self._analysis_ready else "No exports"
        )
        self._backend_summary_label = QLabel("")
        self._backend_summary_label.setWordWrap(True)
        self._export_status_label.setWordWrap(True)
        apply_text_role(self._backend_summary_label, "meta")
        apply_text_role(self._export_status_label, "meta")
        self._export_model_button.setObjectName("ExportActionButton")
        self._save_measurements_button.setIcon(
            build_svg_icon(
                SAVE_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self._save_measurements_button.devicePixelRatioF(),
                tint=THEME_COLORS.focus,
            )
        )
        self._save_measurements_button.setIconSize(major_button_icon_size())
        self._export_model_button.setIcon(
            build_svg_icon(
                SAVE_ICON_PATH,
                major_button_icon_size(),
                device_pixel_ratio=self._export_model_button.devicePixelRatioF(),
                tint=THEME_COLORS.info,
            )
        )
        self._export_model_button.setIconSize(major_button_icon_size())
        blocked_viewport_message = (
            render_backend.viewport_message()
            if render_backend is not None
            else "Interactive 3D disabled."
        )

        self._front_viewport = OrthographicMeshViewport(
            "AP",
            "front",
            show_demo_scene=self._has_model_scene,
            models=self._scene_models,
            interactive_enabled=self._interactive_3d_enabled,
            fallback_message=blocked_viewport_message,
        )
        self._side_viewport = OrthographicMeshViewport(
            "Lat",
            "side",
            show_demo_scene=self._has_model_scene,
            models=self._scene_models,
            interactive_enabled=self._interactive_3d_enabled,
            fallback_message=blocked_viewport_message,
        )
        self._viewport = SpineViewport3D(
            "3D",
            show_demo_scene=self._has_model_scene,
            models=self._scene_models,
            show_display_controls=False,
            interactive_enabled=self._interactive_3d_enabled,
            fallback_message=blocked_viewport_message,
        )
        self._measurement_overlay_controller = MeasurementOverlayController(
            self._viewport,
            self._load_landmarks_payload,
        )

        self._measurement_name_label = QLabel("")
        self._measurement_value_label = QLabel("")
        self._measurement_unit_label = QLabel("")
        self._measurement_confidence_label = QLabel("")
        self._measurement_included_label = QLabel("")
        self._measurement_stage_label = QLabel("")
        self._measurement_source_label = QLabel("")
        self._active_vertebra_label = QLabel("")
        self._reference_vertebra_label = QLabel("")
        self._global_axis_label = QLabel("")
        self._selected_vertebrae_label = QLabel("")
        self._delta_x_label = QLabel("")
        self._delta_y_label = QLabel("")
        self._delta_z_label = QLabel("")
        self._distance_label = QLabel("")
        self._mesh_source_label = QLabel("")
        for label in (
            self._measurement_name_label,
            self._measurement_value_label,
            self._measurement_unit_label,
            self._measurement_confidence_label,
            self._measurement_included_label,
            self._measurement_stage_label,
            self._measurement_source_label,
            self._active_vertebra_label,
            self._reference_vertebra_label,
            self._global_axis_label,
            self._selected_vertebrae_label,
            self._delta_x_label,
            self._delta_y_label,
            self._delta_z_label,
            self._distance_label,
            self._mesh_source_label,
        ):
            label.setWordWrap(True)
            apply_text_role(label, "body")

        self._measurement_buttons: dict[str, MeasurementSelectionButton] = {}
        self._measurement_items: dict[str, QTreeWidgetItem] = {}
        self._vertebra_buttons: dict[tuple[str, str], VertebraSelectionButton] = {}
        self._manual_tool_buttons: dict[str, ManualMeasurementToolButton] = {}
        self._pose_visibility_buttons: dict[str, CapsuleButton] = {}
        self._display_mode_buttons: dict[ViewportMode, CapsuleButton] = {}
        self._display_detail_buttons: dict[int, CapsuleButton] = {}
        self._point_size_slider: QSlider | None = None
        self._left_action_card: QFrame | None = None
        self._motion_matrix_headers: dict[str, QLabel] = {}
        self._motion_matrix_value_labels: dict[tuple[str, str], QLabel] = {}
        self._motion_matrix_frame = QFrame()
        self._motion_matrix_frame.setObjectName("InspectorInfoGrid")
        self._motion_matrix_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self._motion_matrix_layout = QGridLayout(self._motion_matrix_frame)
        self._motion_matrix_layout.setContentsMargins(0, 0, 0, 0)
        self._motion_matrix_layout.setHorizontalSpacing(GEOMETRY.unit)
        self._motion_matrix_layout.setVerticalSpacing(max(1, GEOMETRY.unit // 2))
        self._motion_matrix_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._pending_viewport_fit = self._analysis_ready and self._has_model_scene

        super().__init__(
            "measurement",
            "Measurement",
            f"Case {manifest.case_id} · {manifest.patient_name}",
            settings,
            self._build_left_panel(),
            self._build_center_panel(),
            self._build_right_panel(),
        )

        self._connect_signals()
        self._populate_anatomy_tree()
        self._populate_measurement_tree()
        self._populate_vertebra_buttons()
        self.apply_shared_display_state(
            mode=self._initial_viewport_mode,
            detail_level=self._initial_detail_level,
            point_size=self._initial_point_size,
            baseline_visible=self._initial_baseline_pose_visible,
            standing_visible=self._initial_standing_pose_visible,
        )
        self.apply_shared_selection_state(
            selected_ids=self._initial_selected_ids,
            active_id=self._initial_active_id,
            reference_id=self._initial_reference_id,
            isolate_selection=self._initial_isolate_selection,
        )
        self._refresh_summaries()
        self._refresh_measurement_details()
        self._refresh_measurement_overlay()
        self._refresh_motion_details()
        self._refresh_mesh_details()
        self.refresh_backend_provenance()
        self._apply_vertebra_selection()
        self._sync_manual_picking_mode()
        self._shared_state_callbacks_enabled = True

    def dispose(self) -> None:
        set_callback = getattr(self._viewport, "set_surface_point_pick_callback", None)
        if callable(set_callback):
            set_callback(None)
        set_enabled = getattr(self._viewport, "set_surface_point_picking_enabled", None)
        if callable(set_enabled):
            set_enabled(False)
        self._measurement_overlay_controller.clear()
        self._clear_manual_measurement_session()
        self._viewport.dispose()
        self._front_viewport.dispose()
        self._side_viewport.dispose()

    def _build_left_panel(self) -> PanelFrame:
        panel = PanelFrame(
            "Measurements",
            (
                "Choose measurements to save, then select vertebrae or pelvis. "
                "Use Set Reference Frame to make the current selection the motion basis."
            )
            if self._analysis_ready
            else "Run Analyze in Import.",
            settings=self._workspace_settings,
            workspace_id="measurement",
            panel_id="left",
        )
        panel.add_widget(self._anatomy_tree, stretch=1, title="Anatomy Explorer")
        panel.add_widget(self._measurement_tree, stretch=2, title="Measurement Explorer")
        panel.add_widget(self._build_vertebra_selection_section(), title="Vertebrae")

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

        summaries_row = QHBoxLayout()
        summaries_row.setContentsMargins(0, 0, 0, 0)
        summaries_row.setSpacing(GEOMETRY.inspector_row_gap)
        summaries_row.addWidget(self._selected_summary)
        summaries_row.addWidget(self._vertebra_summary)
        action_layout.addLayout(summaries_row)
        action_layout.addWidget(self._overlay_status_label)

        self._isolate_button.setFixedHeight(GEOMETRY.major_button_height)
        self._isolate_button.setObjectName("MeasurementActionButton")
        self._save_measurements_button.setFixedHeight(GEOMETRY.major_button_height)
        self._export_model_button.setFixedHeight(GEOMETRY.major_button_height)
        self._clear_selection_button.setFixedHeight(GEOMETRY.major_button_height)
        self._set_reference_frame_button.setFixedHeight(GEOMETRY.major_button_height)
        self._clear_selection_button.setObjectName("MeasurementActionButton")
        self._set_reference_frame_button.setObjectName("MeasurementActionButton")
        for button in (self._save_measurements_button, self._export_model_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if not self._analysis_ready:
            for button in (
                self._isolate_button,
                self._clear_selection_button,
                self._set_reference_frame_button,
                self._save_measurements_button,
                self._export_model_button,
            ):
                button.setEnabled(False)

        action_layout.addWidget(self._build_pose_visibility_action_row())

        isolate_action_row = QFrame()
        isolate_action_row.setObjectName("InspectorInfoRow")
        isolate_actions = QHBoxLayout(isolate_action_row)
        isolate_actions.setContentsMargins(0, 0, 0, 0)
        isolate_actions.setSpacing(GEOMETRY.unit)
        self._isolate_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._clear_selection_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        isolate_actions.addWidget(self._isolate_button)
        isolate_actions.addWidget(self._clear_selection_button)
        isolate_actions.setStretch(0, 1)
        isolate_actions.setStretch(1, 1)

        action_layout.addWidget(self._set_reference_frame_button)
        action_layout.addWidget(isolate_action_row)
        action_layout.addWidget(self._save_measurements_button)
        action_layout.addWidget(self._export_model_button)
        action_layout.addWidget(self._backend_summary_label)
        action_layout.addWidget(self._export_status_label)
        panel.outer_layout.addWidget(action_card)
        return panel

    def _build_vertebra_selection_section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelInner")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(max(1, GEOMETRY.unit // 2))
        baseline_header = QLabel("Supine")
        baseline_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(baseline_header, "micro")
        header_row.addWidget(baseline_header, stretch=1)
        standing_header = QLabel("Standing")
        standing_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(standing_header, "micro")
        standing_header.setVisible(self._has_comparison_scene)
        header_row.addWidget(standing_header, stretch=1)
        self._standing_vertebra_header = standing_header
        layout.addLayout(header_row)

        self._vertebra_button_container = QFrame()
        self._vertebra_button_container.setObjectName("InspectorInfoRow")
        self._vertebra_button_layout = QGridLayout(self._vertebra_button_container)
        self._vertebra_button_layout.setContentsMargins(0, 0, 0, 0)
        self._vertebra_button_layout.setHorizontalSpacing(max(1, GEOMETRY.unit // 2))
        self._vertebra_button_layout.setVerticalSpacing(max(1, GEOMETRY.unit // 4))
        self._vertebra_button_layout.setColumnStretch(0, 1)
        self._vertebra_button_layout.setColumnStretch(1, 1)
        layout.addWidget(self._vertebra_button_container)
        return frame

    def _build_center_panel(self) -> QFrame:
        if not self._analysis_ready:
            return self._build_pending_center_panel()
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

        toolbar = self._build_manual_measurement_toolbar()
        frame_layout.addWidget(toolbar)

        layout = TransparentSplitter(Qt.Orientation.Horizontal)
        orthographic_stack = TransparentSplitter(Qt.Orientation.Vertical)
        self._center_splitter = layout
        self._orthographic_splitter = orthographic_stack
        layout.setHandleWidth(GEOMETRY.viewport_gap)
        orthographic_stack.setHandleWidth(GEOMETRY.viewport_gap)

        orthographic_stack.addWidget(NestedBubbleFrame(self._front_viewport))
        orthographic_stack.addWidget(NestedBubbleFrame(self._side_viewport))
        orthographic_stack.setStretchFactor(0, 1)
        orthographic_stack.setStretchFactor(1, 1)
        orthographic_stack.setSizes([1, 1])

        layout.addWidget(orthographic_stack)
        layout.addWidget(NestedBubbleFrame(self._viewport))
        layout.setStretchFactor(0, 1)
        layout.setStretchFactor(1, 1)
        layout.setSizes([1, 1])
        schedule_splitter_midpoint(orthographic_stack)
        schedule_splitter_midpoint(layout)
        frame_layout.addWidget(layout, stretch=1)
        return frame

    def _build_pending_center_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("PanelInner")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
        )
        frame_layout.setSpacing(GEOMETRY.viewport_gap)

        layout = TransparentSplitter(Qt.Orientation.Horizontal)
        orthographic_stack = TransparentSplitter(Qt.Orientation.Vertical)
        layout.setHandleWidth(GEOMETRY.viewport_gap)
        orthographic_stack.setHandleWidth(GEOMETRY.viewport_gap)

        orthographic_stack.addWidget(self._build_pending_analysis_viewport("AP"))
        orthographic_stack.addWidget(self._build_pending_analysis_viewport("Lat"))
        orthographic_stack.setStretchFactor(0, 1)
        orthographic_stack.setStretchFactor(1, 1)
        orthographic_stack.setSizes([1, 1])

        layout.addWidget(orthographic_stack)
        layout.addWidget(self._build_pending_analysis_viewport("3D"))
        layout.setStretchFactor(0, 1)
        layout.setStretchFactor(1, 1)
        layout.setSizes([1, 1])
        schedule_splitter_midpoint(orthographic_stack)
        schedule_splitter_midpoint(layout)
        frame_layout.addWidget(layout, stretch=1)
        return frame

    def _build_pending_analysis_viewport(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ViewportCardFrame")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
            GEOMETRY.default_padding,
        )
        layout.setSpacing(GEOMETRY.unit * 2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)
        title_chip = QLabel(title)
        title_chip.setObjectName("ViewportOverlayChip")
        apply_text_role(title_chip, "panel-title")
        title_row.addWidget(title_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        layout.addStretch(1)

        warning_frame = QFrame()
        warning_frame.setObjectName("PendingAnalysisViewport")
        warning_layout = QVBoxLayout(warning_frame)
        warning_layout.setContentsMargins(0, 0, 0, 0)
        warning_layout.setSpacing(GEOMETRY.unit * 2)
        warning_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_bubble = QLabel()
        icon_bubble.setObjectName("InspectorEmptyBubble")
        icon_bubble.setFixedSize(GEOMETRY.control_height_sm, GEOMETRY.control_height_sm)
        icon_bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_bubble.setPixmap(
            build_svg_pixmap(
                PENDING_ANALYSIS_ICON_PATH,
                QSize(
                    TEXT_STYLES["body-emphasis"].line_height,
                    TEXT_STYLES["body-emphasis"].line_height,
                ),
                device_pixel_ratio=icon_bubble.devicePixelRatioF(),
                tint=THEME_COLORS.danger,
            )
        )
        warning_layout.addWidget(icon_bubble, alignment=Qt.AlignmentFlag.AlignHCenter)

        message_label = QLabel("No Analysis Performed")
        message_label.setObjectName("PendingAnalysisMessage")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_text_role(message_label, "body-emphasis")
        warning_layout.addWidget(message_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        hint_label = QLabel("Run Analyze in Import to load models and values.")
        hint_label.setObjectName("PendingAnalysisHint")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        hint_label.setMaximumWidth(GEOMETRY.sidebar_min)
        apply_text_role(hint_label, "meta")
        warning_layout.addWidget(hint_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout.addWidget(warning_frame, stretch=1)
        layout.addStretch(1)
        return frame

    def _build_manual_measurement_toolbar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ManualMeasurementToolbar")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        for tool_id, tooltip in (
            ("select", "Select"),
            ("distance", "Linear distance"),
            ("angle", "Angle"),
        ):
            button = ManualMeasurementToolButton(tool_id, tooltip)
            button.tool_selected.connect(self._set_manual_tool)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignVCenter)
            self._manual_tool_buttons[tool_id] = button

        layout.addStretch(1)
        layout.addWidget(
            self._build_render_mode_group(),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(
            self._build_toolbar_detail_group(),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(
            self._build_point_size_group(),
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        self._refresh_manual_tool_buttons()
        self._refresh_display_controls()
        return frame

    def _build_pose_visibility_action_row(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("InspectorInfoRow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GEOMETRY.unit)

        for pose_name, label in (("baseline", "Supine"), ("standing", "Standing")):
            button = CapsuleButton(label, checkable=True)
            button.setObjectName("PoseVisibilityButton")
            button.setFixedHeight(GEOMETRY.major_button_height)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(
                lambda checked=False, selected_pose=pose_name: self._set_pose_visible(
                    selected_pose,
                    checked,
                )
            )
            layout.addWidget(button)
            self._pose_visibility_buttons[pose_name] = button

        layout.setStretch(0, 1)
        layout.setStretch(1, 1)
        return frame

    def _build_render_mode_group(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CenterToolbarGroup")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        mode_icon_size = QSize(
            TEXT_STYLES["body-emphasis"].line_height,
            TEXT_STYLES["body-emphasis"].line_height,
        )
        for mode in ViewportMode:
            button = CapsuleButton("", checkable=True)
            button.setObjectName("ViewportModeButton")
            button.setToolTip(mode.value.title())
            button.setAccessibleName(mode.value.title())
            button.setFixedSize(
                GEOMETRY.toolbar_control_size,
                GEOMETRY.toolbar_control_size,
            )
            button.setIconSize(mode_icon_size)
            button.clicked.connect(
                lambda checked=False, selected_mode=mode: self._viewport.set_mode(selected_mode)
            )
            layout.addWidget(button)
            self._display_mode_buttons[mode] = button
        return frame

    def _build_toolbar_detail_group(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CenterToolbarGroup")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        for button_label, button_level in DETAIL_PRESET_LEVELS:
            button = CapsuleButton(button_label, checkable=True)
            button.setObjectName("ViewportAxisButton")
            button.setFixedSize(
                GEOMETRY.toolbar_control_size + (GEOMETRY.default_padding * 2),
                GEOMETRY.toolbar_control_size,
            )
            button.clicked.connect(
                lambda checked=False, selected_level=button_level: self._viewport.set_detail_level(
                    selected_level
                )
            )
            layout.addWidget(button)
            self._display_detail_buttons[button_level] = button
        return frame

    def _build_point_size_group(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("CenterToolbarGroup")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
            GEOMETRY.default_padding,
            GEOMETRY.inspector_row_gap,
        )
        layout.setSpacing(GEOMETRY.inspector_row_gap)

        label = QLabel("Points")
        apply_text_role(label, "meta")
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName("PointSizeSlider")
        slider.setRange(2, 24)
        slider.setFixedWidth(GEOMETRY.unit * 10)
        slider.valueChanged.connect(self._handle_point_size_slider_changed)
        layout.addWidget(slider)
        self._point_size_slider = slider
        return frame

    def _build_right_panel(self) -> PanelFrame:
        panel = PanelFrame(
            "Inspector",
            "Measurement targets and primary-relative motion",
            settings=self._workspace_settings,
            workspace_id="measurement",
            panel_id="right",
        )

        measurement_card = QFrame()
        measurement_card.setObjectName("PanelInner")
        measurement_layout = QVBoxLayout(measurement_card)
        measurement_layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        measurement_layout.setSpacing(max(1, GEOMETRY.unit // 2))
        measurement_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        measurement_layout.addWidget(
            self._build_compact_detail_grid(
                (
                    ("Metric", self._measurement_name_label),
                    ("Value", self._measurement_value_label),
                    ("Unit", self._measurement_unit_label),
                    ("Included", self._measurement_included_label),
                    ("Confidence", self._measurement_confidence_label),
                    ("Stage", self._measurement_stage_label),
                ),
                full_width_pairs=(("Source", self._measurement_source_label),),
            )
        )
        panel.add_widget(measurement_card, stretch=1, title="Measurement")

        motion_card = QFrame()
        motion_card.setObjectName("PanelInner")
        motion_layout = QVBoxLayout(motion_card)
        motion_layout.setContentsMargins(
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
            GEOMETRY.inspector_padding,
        )
        motion_layout.setSpacing(max(1, GEOMETRY.unit // 2))
        motion_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        motion_layout.addWidget(
            self._build_compact_detail_grid(
                (
                    ("Primary", self._reference_vertebra_label),
                    ("Latest", self._active_vertebra_label),
                    ("Global Axis", self._global_axis_label),
                ),
                full_width_pairs=(
                    ("Compared", self._selected_vertebrae_label),
                    ("Mesh", self._mesh_source_label),
                ),
            )
        )
        motion_layout.addWidget(self._motion_matrix_frame)
        panel.add_widget(motion_card, stretch=2, title="Motion")

        return panel

    def _build_compact_detail_grid(
        self,
        detail_pairs: tuple[tuple[str, QLabel], ...],
        *,
        columns: int = 2,
        full_width_pairs: tuple[tuple[str, QLabel], ...] = (),
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("InspectorInfoGrid")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(GEOMETRY.unit)
        layout.setVerticalSpacing(max(1, GEOMETRY.unit // 2))
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for index, (title, value_label) in enumerate(detail_pairs):
            row = index // columns
            column = index % columns
            layout.addWidget(self._build_compact_detail_row(title, value_label), row, column)

        base_row = (len(detail_pairs) + max(columns - 1, 0)) // columns
        for title, value_label in full_width_pairs:
            layout.addWidget(
                self._build_compact_detail_row(title, value_label),
                base_row,
                0,
                1,
                columns,
            )
            base_row += 1

        for column in range(columns):
            layout.setColumnStretch(column, 1)
        return frame

    def _build_compact_detail_row(self, title: str, value_label: QLabel) -> QFrame:
        group = QFrame()
        group.setObjectName("InspectorInfoRow")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(max(1, GEOMETRY.unit // 2))

        title_label = QLabel(title)
        apply_text_role(title_label, "micro")
        title_label.setMinimumWidth(GEOMETRY.unit * 7)
        layout.addWidget(title_label)
        layout.addWidget(value_label, stretch=1)
        return group

    def _connect_signals(self) -> None:
        self._measurement_tree.currentItemChanged.connect(self._handle_measurement_selection_changed)
        self._save_measurements_button.clicked.connect(self._save_measurements)
        self._export_model_button.clicked.connect(self._export_model)
        self._set_reference_frame_button.clicked.connect(self._set_reference_frame)
        self._isolate_button.toggled.connect(self._toggle_isolate_selection)
        self._clear_selection_button.clicked.connect(self._clear_selection)
        self._viewport.mode_changed.connect(self._handle_viewport_mode_changed)
        self._viewport.detail_level_changed.connect(self._handle_viewport_detail_changed)
        self._viewport.point_size_changed.connect(self._handle_viewport_point_size_changed)
        self._viewport.selection_changed.connect(self._handle_viewport_selection)
        self._front_viewport.selection_changed.connect(self._handle_viewport_selection)
        self._side_viewport.selection_changed.connect(self._handle_viewport_selection)
        self._sync_orthographic_viewport_mode(self._viewport.current_mode())
        self._sync_orthographic_viewport_detail(self._viewport.current_detail_level())
        self._sync_orthographic_viewport_point_size(self._viewport.current_point_size())
        self._refresh_display_controls()

    def _populate_anatomy_tree(self) -> None:
        label_names = {model.vertebra_id for model in self._scene_models}
        groups = available_anatomy_groups(label_names)
        self._anatomy_tree.populate(groups)
        self._anatomy_tree.visibility_changed.connect(
            self._handle_anatomy_visibility_changed
        )

    def _handle_anatomy_visibility_changed(self, visible_labels: set[str]) -> None:
        if hasattr(self, "_viewport"):
            self._viewport.set_label_visibility(visible_labels)
        for vp in getattr(self, "_orthographic_viewports", {}).values():
            if hasattr(vp, "set_label_visibility"):
                vp.set_label_visibility(visible_labels)

    def _populate_measurement_tree(self) -> None:
        self._measurement_tree.clear()
        self._measurement_buttons.clear()
        self._measurement_items.clear()

        header = self._measurement_tree.header()
        if header is not None:
            header.setSectionResizeMode(0, header.ResizeMode.Stretch)
            header.setSectionResizeMode(1, header.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, header.ResizeMode.Fixed)
            self._measurement_tree.setColumnWidth(2, GEOMETRY.control_height_sm + GEOMETRY.unit)

        root_item = QTreeWidgetItem(["Measurement Set", "", ""])
        root_item.setFlags(root_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._measurement_tree.addTopLevelItem(root_item)

        for measurement_record in self._measurement_records:
            measurement_name = measurement_record_label(measurement_record)
            measurement_value = measurement_record.value_text
            item = QTreeWidgetItem(root_item)
            item.setText(0, measurement_name)
            item.setText(1, measurement_value)
            item.setData(
                1,
                Qt.ItemDataRole.TextAlignmentRole,
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            )
            item.setData(0, Qt.ItemDataRole.UserRole, measurement_name)

            button = MeasurementSelectionButton()
            button.toggled.connect(
                lambda checked, key=measurement_name: self._handle_measurement_toggle(key, checked)
            )
            self._measurement_tree.setItemWidget(item, 2, button)
            self._measurement_buttons[measurement_name] = button
            self._measurement_items[measurement_name] = item

        root_item.setExpanded(True)
        first_item = root_item.child(0)
        if first_item is not None:
            self._measurement_tree.setCurrentItem(first_item)

    def _populate_vertebra_buttons(self) -> None:
        while self._vertebra_button_layout.count():
            item = self._vertebra_button_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        self._vertebra_buttons.clear()
        if not self._model_ids:
            empty_label = QLabel("No vertebrae")
            empty_label.setWordWrap(True)
            apply_text_role(empty_label, "meta")
            self._vertebra_button_layout.addWidget(empty_label, 0, 0, 1, 2)
            return

        for row, vertebra_id in enumerate(self._model_ids):
            baseline_button = VertebraSelectionButton(vertebra_id)
            baseline_button.interaction_requested.connect(self._handle_vertebra_button_interaction)
            self._vertebra_button_layout.addWidget(baseline_button, row, 0)
            self._vertebra_buttons[("baseline", vertebra_id)] = baseline_button

            if self._has_comparison_scene and vertebra_id in self._standing_index:
                standing_button = VertebraSelectionButton(vertebra_id)
                standing_button.interaction_requested.connect(
                    self._handle_vertebra_button_interaction
                )
                self._vertebra_button_layout.addWidget(standing_button, row, 1)
                self._vertebra_buttons[("standing", vertebra_id)] = standing_button

    def _refresh_summaries(self) -> None:
        selected_measurement_count = len(self._selected_measurements())
        total_measurement_count = len(self._measurement_values)
        self._selected_summary.value_label.setText(
            f"{selected_measurement_count} / {total_measurement_count}"
        )
        self._vertebra_summary.value_label.setText(str(len(self._selection_state.selected_ids)))

    def _set_manual_tool(self, tool_id: str) -> None:
        if tool_id not in self._manual_tool_buttons:
            return
        if tool_id == self._manual_tool:
            self._refresh_manual_tool_buttons()
            self._sync_manual_picking_mode()
            return
        self._manual_tool = tool_id
        self._clear_manual_measurement_session()
        self._refresh_manual_tool_buttons()
        self._sync_manual_picking_mode()
        self._refresh_measurement_overlay()

    def _refresh_manual_tool_buttons(self) -> None:
        icon_size = QSize(
            TEXT_STYLES["body-emphasis"].line_height,
            TEXT_STYLES["body-emphasis"].line_height,
        )
        for tool_id, button in self._manual_tool_buttons.items():
            is_active = tool_id == self._manual_tool
            button.setChecked(is_active)
            tint = THEME_COLORS.focus if is_active else THEME_COLORS.text_primary
            button.setIcon(
                build_svg_icon(
                    MANUAL_TOOL_ICON_PATHS[tool_id],
                    icon_size,
                    device_pixel_ratio=button.devicePixelRatioF(),
                    tint=tint,
                )
            )
            button.setIconSize(icon_size)
            refresh_widget_style(button)

    def _sync_manual_picking_mode(self) -> None:
        enabled = self._analysis_ready and self._manual_tool in {"distance", "angle"}
        set_callback = getattr(self._viewport, "set_surface_point_pick_callback", None)
        set_enabled = getattr(self._viewport, "set_surface_point_picking_enabled", None)
        if callable(set_callback):
            set_callback(self._handle_manual_point_picked if enabled else None)
        if callable(set_enabled):
            set_enabled(enabled)
        self._overlay_status_label.setText(self._manual_overlay_status_text())

    def _manual_overlay_status_text(self) -> str:
        if not self._analysis_ready:
            return "Run Analyze to inspect overlays and use manual tools."
        if self._manual_tool == "distance":
            if len(self._manual_measurement_points) >= 2:
                return f"Distance: {self._manual_distance_text()}"
            if len(self._manual_measurement_points) == 1:
                return "Distance tool: click a second point."
            return "Distance tool: click a first point on visible anatomy."
        if self._manual_tool == "angle":
            if len(self._manual_measurement_points) >= 3:
                return f"Angle: {self._manual_angle_text()}"
            if len(self._manual_measurement_points) == 2:
                return "Angle tool: click a third point."
            if len(self._manual_measurement_points) == 1:
                return "Angle tool: click a second point."
            return "Angle tool: click a first point on visible anatomy."
        return self._overlay_status_text()

    def _overlay_status_text(self) -> str:
        if not self._analysis_ready:
            return "Run Analyze to inspect automatic measurement overlays."
        if self._selected_measurement:
            return f"Automatic overlay: {self._selected_measurement}"
        return "Automatic overlay unavailable for the selected measurement."

    def _refresh_measurement_overlay(self) -> None:
        geometry = self._measurement_overlay_controller.refresh(self._selected_measurement)
        if self._manual_tool == "select":
            overlay_text = (
                self._overlay_status_text()
                if geometry is not None
                else "Automatic overlay unavailable for the selected measurement."
            )
            self._overlay_status_label.setText(overlay_text)

    def _clear_manual_measurement_session(self) -> None:
        self._manual_measurement_points = []
        clear_overlay = getattr(self._viewport, "clear_overlay_geometry", None)
        if callable(clear_overlay):
            clear_overlay("manual-measurement")
        if self._manual_tool != "select":
            self._overlay_status_label.setText(self._manual_overlay_status_text())

    def _handle_manual_point_picked(self, point: tuple[float, float, float]) -> None:
        if self._manual_tool not in {"distance", "angle"}:
            return
        required_points = 2 if self._manual_tool == "distance" else 3
        if len(self._manual_measurement_points) >= required_points:
            self._manual_measurement_points = []
        self._manual_measurement_points.append(point)
        self._refresh_manual_measurement_overlay()
        self._overlay_status_label.setText(self._manual_overlay_status_text())

    def _refresh_manual_measurement_overlay(self) -> None:
        geometry = self._manual_measurement_geometry()
        set_overlay = getattr(self._viewport, "set_overlay_geometry", None)
        if callable(set_overlay):
            set_overlay("manual-measurement", geometry)

    def _manual_measurement_geometry(self) -> OverlayGeometry | None:
        points = tuple(self._manual_measurement_points)
        if not points or self._manual_tool == "select":
            return None
        if self._manual_tool == "distance":
            if len(points) == 1:
                return OverlayGeometry(
                    overlay_id="manual-measurement",
                    label="Distance",
                    anchor_points=points,
                    line_color=THEME_COLORS.focus_reference,
                    point_color=THEME_COLORS.focus_reference,
                    line_width=4,
                    point_size=20,
                )
            return OverlayGeometry(
                overlay_id="manual-measurement",
                label=f"Distance: {self._manual_distance_text()}",
                line_segments=((points[0], points[1]),),
                anchor_points=points[:2],
                line_color=THEME_COLORS.focus_reference,
                point_color=THEME_COLORS.focus_reference,
                line_width=4,
                point_size=20,
            )
        if len(points) < 2:
            return OverlayGeometry(
                overlay_id="manual-measurement",
                label="Angle",
                anchor_points=points,
                line_color=THEME_COLORS.focus_reference,
                point_color=THEME_COLORS.focus_reference,
                line_width=4,
                point_size=20,
            )
        if len(points) == 2:
            return OverlayGeometry(
                overlay_id="manual-measurement",
                label="Angle",
                line_segments=((points[1], points[0]),),
                anchor_points=points,
                line_color=THEME_COLORS.focus_reference,
                point_color=THEME_COLORS.focus_reference,
                line_width=4,
                point_size=20,
            )
        line_segments = ((points[1], points[0]), (points[1], points[2]))
        return OverlayGeometry(
            overlay_id="manual-measurement",
            label=f"Angle: {self._manual_angle_text()}",
            line_segments=line_segments,
            anchor_points=points[:3],
            line_color=THEME_COLORS.focus_reference,
            point_color=THEME_COLORS.focus_reference,
            line_width=4,
            point_size=20,
        )

    def _manual_distance_text(self) -> str:
        if len(self._manual_measurement_points) < 2:
            return "—"
        return f"{self._manual_distance_value():.1f} mm"

    def _manual_angle_text(self) -> str:
        if len(self._manual_measurement_points) < 3:
            return "—"
        return f"{self._manual_angle_value():.1f} deg"

    def _manual_distance_value(self) -> float:
        if len(self._manual_measurement_points) < 2:
            return 0.0
        from math import dist

        start = cast(tuple[float, float, float], self._manual_measurement_points[0])
        end = cast(tuple[float, float, float], self._manual_measurement_points[1])
        return dist(start, end)

    def _manual_angle_value(self) -> float:
        if len(self._manual_measurement_points) < 3:
            return 0.0
        from math import acos, degrees

        first = cast(tuple[float, float, float], self._manual_measurement_points[0])
        vertex = cast(tuple[float, float, float], self._manual_measurement_points[1])
        third = cast(tuple[float, float, float], self._manual_measurement_points[2])
        vector_a = (
            first[0] - vertex[0],
            first[1] - vertex[1],
            first[2] - vertex[2],
        )
        vector_b = (
            third[0] - vertex[0],
            third[1] - vertex[1],
            third[2] - vertex[2],
        )
        norm_a = sum(component * component for component in vector_a) ** 0.5
        norm_b = sum(component * component for component in vector_b) ** 0.5
        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0
        cosine = (
            vector_a[0] * vector_b[0]
            + vector_a[1] * vector_b[1]
            + vector_a[2] * vector_b[2]
        ) / (norm_a * norm_b)
        cosine = max(-1.0, min(1.0, cosine))
        return degrees(acos(cosine))

    def _refresh_display_controls(self) -> None:
        self._refresh_pose_visibility_buttons()
        self._refresh_display_mode_buttons(self._viewport.current_mode())
        self._refresh_display_detail_buttons(self._viewport.current_detail_level())
        self._refresh_point_size_slider(self._viewport.current_point_size())

    def _refresh_pose_visibility_buttons(self) -> None:
        baseline_button = self._pose_visibility_buttons.get("baseline")
        if baseline_button is not None:
            baseline_button.blockSignals(True)
            baseline_button.setChecked(self._baseline_pose_visible)
            baseline_button.setEnabled(self._analysis_ready)
            baseline_button.setProperty(
                "visibilityState",
                "shown" if self._baseline_pose_visible else "hidden",
            )
            baseline_button.blockSignals(False)
            refresh_widget_style(baseline_button)

        standing_button = self._pose_visibility_buttons.get("standing")
        if standing_button is not None:
            standing_button.blockSignals(True)
            standing_button.setChecked(self._standing_pose_visible)
            standing_button.setEnabled(self._analysis_ready and self._has_comparison_scene)
            standing_button.setProperty(
                "visibilityState",
                "shown" if self._standing_pose_visible else "hidden",
            )
            standing_button.blockSignals(False)
            refresh_widget_style(standing_button)

    def _set_pose_visible(self, pose_name: str, visible: bool) -> None:
        if pose_name == "baseline":
            self._baseline_pose_visible = bool(visible)
        elif pose_name == "standing":
            if not self._has_comparison_scene:
                self._standing_pose_visible = False
            else:
                self._standing_pose_visible = bool(visible)
        else:
            return
        self._apply_pose_visibility()
        self._refresh_pose_visibility_buttons()
        self._notify_display_state_changed()

    def _apply_pose_visibility(self) -> None:
        for viewport in (self._viewport, self._front_viewport, self._side_viewport):
            viewport.set_pose_visibility(
                baseline_visible=self._baseline_pose_visible,
                standing_visible=self._standing_pose_visible,
            )

    def _refresh_display_mode_buttons(self, mode: ViewportMode) -> None:
        for button_mode, button in self._display_mode_buttons.items():
            button.setChecked(button_mode == mode)
            tint = THEME_COLORS.focus if button_mode == mode else THEME_COLORS.text_primary
            button.setIcon(
                build_svg_icon(
                    VIEWPORT_MODE_ICON_PATHS[button_mode],
                    button.iconSize(),
                    device_pixel_ratio=button.devicePixelRatioF(),
                    tint=tint,
                )
            )
            refresh_widget_style(button)

    def _refresh_display_detail_buttons(self, detail_level: int) -> None:
        selected_level = detail_preset_level(detail_level)
        for button_level, button in self._display_detail_buttons.items():
            button.setChecked(button_level == selected_level)
            refresh_widget_style(button)

    def _handle_viewport_mode_changed(self, mode: ViewportMode) -> None:
        self._sync_orthographic_viewport_mode(mode)
        self._refresh_display_mode_buttons(mode)
        self._notify_display_state_changed()

    def _handle_viewport_detail_changed(self, detail_level: int) -> None:
        self._sync_orthographic_viewport_detail(detail_level)
        self._refresh_display_detail_buttons(detail_level)
        self._notify_display_state_changed()

    def _handle_viewport_point_size_changed(self, point_size: int) -> None:
        self._sync_orthographic_viewport_point_size(point_size)
        self._refresh_point_size_slider(point_size)
        self._notify_display_state_changed()

    def _handle_point_size_slider_changed(self, point_size: int) -> None:
        self._viewport.set_point_size(point_size)

    def _refresh_measurement_details(self) -> None:
        measurement_name = self._selected_measurement
        measurement_value = self._measurement_values.get(measurement_name, "Not available")
        measurement_record = self._measurement_record_lookup.get(measurement_name)
        included = self._measurement_buttons.get(measurement_name)
        selected_state = "Yes" if included is not None and included.isChecked() else "No"

        self._measurement_name_label.setText(measurement_name or "None")
        self._measurement_value_label.setText(
            measurement_display_value(measurement_record, measurement_value)
        )
        self._measurement_unit_label.setText(
            measurement_record.unit
            if measurement_record is not None and measurement_record.unit
            else "—"
        )
        self._measurement_confidence_label.setText(
            format_measurement_confidence(
                measurement_record.confidence if measurement_record is not None else None
            )
        )
        self._measurement_included_label.setText(selected_state)
        self._measurement_stage_label.setText(
            measurement_stage_text(measurement_record) if measurement_record is not None else "—"
        )
        self._measurement_source_label.setText(
            measurement_source_text(measurement_record, self._manifest.measurements.provenance)
        )

    def _refresh_motion_details(self) -> None:
        selected_ids = self._selection_state.selected_ids
        active_id = self._selection_state.active_id
        reference_id = self._selection_state.reference_id

        self._active_vertebra_label.setText(active_id or "None")
        self._reference_vertebra_label.setText(reference_id or "None")
        self._global_axis_label.setText(
            f"{reference_id} local Z" if reference_id is not None else "None"
        )
        compared_ids = tuple(
            vertebra_id for vertebra_id in selected_ids if vertebra_id != reference_id
        )
        self._selected_vertebrae_label.setText(
            ", ".join(compared_ids)
            if compared_ids
            else ("Select vertebrae or pelvis" if not selected_ids else "Set a reference frame")
        )
        self._rebuild_motion_matrix(reference_id, compared_ids)

    def _refresh_mesh_details(self) -> None:
        mesh_files = collect_mesh_export_sources(
            self._manifest,
            self._selection_state.selected_ids or None,
        )
        if mesh_files:
            if self._has_comparison_scene:
                self._mesh_source_label.setText(
                    f"{len(mesh_files)} baseline meshes · standing overlay"
                )
            else:
                self._mesh_source_label.setText(f"{len(mesh_files)} meshes")
            return
        self._mesh_source_label.setText("No mesh artifact")

    def refresh_backend_provenance(self) -> None:
        summary = summary_for_manifest(self._manifest) or summary_for_active_bundle(
            self._store,
            self._workspace_settings,
        )
        if summary is None:
            self._backend_summary_label.setText("Segmentation backend · Unavailable")
            return
        source_prefix = (
            "Segmentation backend used"
            if summary_for_manifest(self._manifest) is not None
            else "Active backend pending analyze"
        )
        self._backend_summary_label.setText(
            f"{source_prefix} · {summary.compact_label}"
        )

    def _load_landmarks_payload(self) -> dict[str, Any] | None:
        if not self._analysis_ready:
            return None
        artifact = latest_artifact_by_type(self._manifest, "landmarks")
        if artifact is None:
            return None
        artifact_path = Path(artifact.path)
        if not artifact_path.is_file():
            return None
        try:
            payload = read_json_artifact(artifact_path)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _apply_vertebra_selection(self) -> None:
        for (_pose_name, vertebra_id), button in self._vertebra_buttons.items():
            if vertebra_id == self._selection_state.reference_id:
                button.set_selection_state("reference")
            elif vertebra_id in self._selection_state.selected_ids:
                button.set_selection_state("selected")
            else:
                button.set_selection_state("idle")

        self._isolate_button.blockSignals(True)
        self._isolate_button.setChecked(self._selection_state.isolate_selection)
        self._isolate_button.blockSignals(False)
        self._isolate_button.setEnabled(self._analysis_ready)
        self._clear_selection_button.setEnabled(self._analysis_ready)
        can_set_reference = (
            self._analysis_ready
            and self._selection_state.active_id is not None
            and self._selection_state.active_id in set(self._reference_ids)
        )
        self._set_reference_frame_button.setEnabled(can_set_reference)
        action_state = "ready" if self._selection_state.selected_ids else "empty"
        self._isolate_button.setProperty("actionState", action_state)
        self._clear_selection_button.setProperty("actionState", action_state)
        self._set_reference_frame_button.setProperty(
            "actionState",
            "ready" if can_set_reference else "empty",
        )
        refresh_widget_style(self._isolate_button)
        refresh_widget_style(self._clear_selection_button)
        refresh_widget_style(self._set_reference_frame_button)

        self._viewport.set_selection(
            self._selection_state.selected_ids,
            active_id=self._selection_state.active_id,
            reference_id=self._selection_state.reference_id,
            isolate_selection=self._selection_state.isolate_selection,
        )
        self._front_viewport.set_selection(
            self._selection_state.selected_ids,
            active_id=self._selection_state.active_id,
            reference_id=self._selection_state.reference_id,
            isolate_selection=self._selection_state.isolate_selection,
        )
        self._side_viewport.set_selection(
            self._selection_state.selected_ids,
            active_id=self._selection_state.active_id,
            reference_id=self._selection_state.reference_id,
            isolate_selection=self._selection_state.isolate_selection,
        )

        self._refresh_summaries()
        self._refresh_motion_details()
        self._refresh_mesh_details()
        self._notify_selection_state_changed()

    def _rebuild_motion_matrix(
        self,
        primary_id: str | None,
        compared_ids: tuple[str, ...],
    ) -> None:
        clear_layout(self._motion_matrix_layout)
        self._motion_matrix_headers.clear()
        self._motion_matrix_value_labels.clear()

        if primary_id is None:
            empty_label = QLabel("Select a primary vertebra to inspect motion.")
            apply_text_role(empty_label, "meta")
            empty_label.setWordWrap(True)
            self._motion_matrix_layout.addWidget(empty_label, 0, 0, 1, 2)
            return

        if not compared_ids:
            empty_label = QLabel("Select another vertebra to compare against the primary.")
            apply_text_role(empty_label, "meta")
            empty_label.setWordWrap(True)
            self._motion_matrix_layout.addWidget(empty_label, 0, 0, 1, 2)
            return

        metric_columns = (
            ("delta_x", "ΔX"),
            ("delta_y", "ΔY"),
            ("delta_z", "ΔZ"),
            ("distance", "Dist"),
        )

        row_header = QLabel("Vertebra")
        apply_text_role(row_header, "micro")
        self._motion_matrix_layout.addWidget(row_header, 0, 0)

        column_ids = (primary_id, *compared_ids)
        row_values_by_vertebra: dict[str, dict[str, str]] = {
            primary_id: {
                "delta_x": format_delta(0.0),
                "delta_y": format_delta(0.0),
                "delta_z": format_delta(0.0),
                "distance": "0.00",
            }
        }
        for vertebra_id in compared_ids:
            metrics = compute_relative_motion_metrics(
                vertebra_id,
                primary_id,
                self._model_index,
                self._standing_index,
            )
            row_values_by_vertebra[vertebra_id] = {
                "delta_x": format_delta(metrics.delta_x) if metrics is not None else "—",
                "delta_y": format_delta(metrics.delta_y) if metrics is not None else "—",
                "delta_z": format_delta(metrics.delta_z) if metrics is not None else "—",
                "distance": f"{metrics.distance:.2f}" if metrics is not None else "—",
            }

        for column, (_metric_key, metric_label) in enumerate(metric_columns, start=1):
            metric_label_widget = QLabel(metric_label)
            metric_label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            apply_text_role(metric_label_widget, "micro")
            self._motion_matrix_layout.addWidget(metric_label_widget, 0, column)

        for row, vertebra_id in enumerate(column_ids, start=1):
            header_label = QLabel(vertebra_id)
            header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            apply_text_role(header_label, "body-emphasis")
            self._motion_matrix_layout.addWidget(header_label, row, 0)
            self._motion_matrix_headers[vertebra_id] = header_label

            for column, (metric_key, _metric_label) in enumerate(metric_columns, start=1):
                value_label = QLabel(row_values_by_vertebra[vertebra_id][metric_key])
                value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                apply_text_role(value_label, "body")
                self._motion_matrix_layout.addWidget(value_label, row, column)
                self._motion_matrix_value_labels[(vertebra_id, metric_key)] = value_label

        self._motion_matrix_layout.setColumnStretch(0, 0)
        for column in range(1, len(metric_columns) + 1):
            self._motion_matrix_layout.setColumnStretch(column, 1)

    def _handle_measurement_selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            return
        measurement_name = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(measurement_name, str) and measurement_name:
            self._selected_measurement = measurement_name
            self._refresh_measurement_details()
            self._refresh_measurement_overlay()

    def _handle_measurement_toggle(self, measurement_name: str, checked: bool) -> None:
        del checked
        if self._selected_measurement == measurement_name:
            self._refresh_measurement_details()
        self._refresh_summaries()

    def apply_shared_display_state(
        self,
        *,
        mode: ViewportMode,
        detail_level: int,
        point_size: int,
        baseline_visible: bool,
        standing_visible: bool,
    ) -> None:
        self._synchronizing_shared_state = True
        try:
            self._baseline_pose_visible = bool(baseline_visible)
            self._standing_pose_visible = bool(standing_visible) and self._has_comparison_scene
            if self._viewport.current_mode() != mode:
                self._viewport.set_mode(mode)
            else:
                self._sync_orthographic_viewport_mode(mode)
                self._refresh_display_mode_buttons(mode)
            if self._viewport.current_detail_level() != detail_level:
                self._viewport.set_detail_level(detail_level)
            else:
                self._sync_orthographic_viewport_detail(detail_level)
                self._refresh_display_detail_buttons(detail_level)
            if self._viewport.current_point_size() != point_size:
                self._viewport.set_point_size(point_size)
            else:
                self._sync_orthographic_viewport_point_size(point_size)
                self._refresh_point_size_slider(point_size)
            self._apply_pose_visibility()
            self._refresh_pose_visibility_buttons()
        finally:
            self._synchronizing_shared_state = False

    def apply_shared_selection_state(
        self,
        *,
        selected_ids: tuple[str, ...],
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
    ) -> None:
        valid_ids = set(self._model_ids)
        reference_valid_ids = set(self._reference_ids)
        normalized_selected_ids = tuple(
            vertebra_id for vertebra_id in selected_ids if vertebra_id in valid_ids
        )
        normalized_reference_id = (
            reference_id.upper()
            if isinstance(reference_id, str) and reference_id.upper() in reference_valid_ids
            else self._default_reference_id
        )
        normalized_active_id = (
            active_id
            if active_id in normalized_selected_ids
            else (normalized_selected_ids[-1] if normalized_selected_ids else None)
        )
        self._synchronizing_shared_state = True
        try:
            self._selection_state = VertebraSelectionState(
                normalized_selected_ids,
                normalized_active_id,
                normalized_reference_id,
                isolate_selection and bool(normalized_selected_ids),
            )
            self._apply_vertebra_selection()
        finally:
            self._synchronizing_shared_state = False

    def _notify_display_state_changed(self) -> None:
        if (
            not self._shared_state_callbacks_enabled
            or self._synchronizing_shared_state
            or self._on_display_state_changed is None
        ):
            return
        self._on_display_state_changed(
            self._viewport.current_mode(),
            self._viewport.current_detail_level(),
            self._viewport.current_point_size(),
            self._baseline_pose_visible,
            self._standing_pose_visible,
        )

    def _notify_selection_state_changed(self) -> None:
        if (
            not self._shared_state_callbacks_enabled
            or self._synchronizing_shared_state
            or self._on_selection_state_changed is None
        ):
            return
        self._on_selection_state_changed(
            self._selection_state.selected_ids,
            self._selection_state.active_id,
            self._selection_state.reference_id,
            self._selection_state.isolate_selection,
        )

    def _selected_measurements(self) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        for measurement_record in self._measurement_records:
            measurement_name = measurement_record_label(measurement_record)
            measurement_value = measurement_record.value_text
            button = self._measurement_buttons.get(measurement_name)
            if button is not None and button.isChecked():
                selected.append((measurement_name, measurement_value))
        return selected

    def _handle_vertebra_button_interaction(
        self,
        vertebra_id: str,
        remove_requested: bool,
        set_primary_requested: bool = False,
    ) -> None:
        del set_primary_requested
        self._selection_state = advance_selection_state(
            self._selection_state,
            vertebra_id,
            remove_requested=remove_requested,
            valid_ids=set(self._model_ids),
            reference_valid_ids=set(self._reference_ids),
            default_reference_id=self._default_reference_id,
        )
        self._apply_vertebra_selection()

    def _handle_viewport_selection(
        self,
        vertebra_id: str,
        remove_requested: bool,
        set_primary_requested: bool = False,
    ) -> None:
        del set_primary_requested
        if not vertebra_id:
            self._selection_state = clear_selection_state(
                self._selection_state,
            )
            self._apply_vertebra_selection()
            return
        self._selection_state = advance_selection_state(
            self._selection_state,
            vertebra_id,
            remove_requested=remove_requested,
            valid_ids=set(self._model_ids),
            reference_valid_ids=set(self._reference_ids),
            default_reference_id=self._default_reference_id,
        )
        self._apply_vertebra_selection()

    def _toggle_isolate_selection(self, isolate_selection: bool) -> None:
        self._selection_state = set_isolate_selection(self._selection_state, isolate_selection)
        self._apply_vertebra_selection()

    def _clear_selection(self) -> None:
        self._selection_state = clear_selection_state(
            self._selection_state,
        )
        self._clear_manual_measurement_session()
        self._apply_vertebra_selection()

    def _set_reference_frame(self) -> None:
        active_id = self._selection_state.active_id
        if active_id is None:
            return
        self._selection_state = set_reference_state(
            self._selection_state,
            active_id,
            valid_reference_ids=set(self._reference_ids),
        )
        self._apply_vertebra_selection()

    def _sync_orthographic_viewport_mode(self, mode: ViewportMode) -> None:
        self._front_viewport.set_mode(mode)
        self._side_viewport.set_mode(mode)

    def _sync_orthographic_viewport_detail(self, detail_level: int) -> None:
        self._front_viewport.set_detail_level(detail_level)
        self._side_viewport.set_detail_level(detail_level)

    def _sync_orthographic_viewport_point_size(self, point_size: int) -> None:
        self._front_viewport.set_point_size(point_size)
        self._side_viewport.set_point_size(point_size)

    def _refresh_point_size_slider(self, point_size: int) -> None:
        if self._point_size_slider is None:
            return
        self._point_size_slider.blockSignals(True)
        self._point_size_slider.setValue(point_size)
        self._point_size_slider.setEnabled(self._analysis_ready)
        self._point_size_slider.blockSignals(False)

    def on_workspace_activated(self) -> None:
        for viewport in (self._viewport, self._front_viewport, self._side_viewport):
            viewport.set_render_widget_visible(True)
        self._apply_pose_visibility()
        self._apply_vertebra_selection()
        self._sync_manual_picking_mode()
        self._refresh_measurement_overlay()
        if self._pending_viewport_fit and self._analysis_ready and self._has_model_scene:
            self._fit_viewports_to_scene()
            self._pending_viewport_fit = False
        self._refresh_viewport_renders()
        QTimer.singleShot(0, self._refresh_viewport_renders)

    def on_workspace_deactivated(self) -> None:
        for viewport in (self._viewport, self._front_viewport, self._side_viewport):
            viewport.set_render_widget_visible(False)

    def _save_measurements(self) -> None:
        self._save_measurements_button.set_busy(True, tint=THEME_COLORS.focus)
        selected_measurements = self._selected_measurements()
        if not selected_measurements:
            self._save_measurements_button.set_busy(False)
            QMessageBox.information(self, "Save Measurements", "No measurements selected.")
            return

        output_directory = QFileDialog.getExistingDirectory(
            self,
            "Choose measurement export folder",
            str(Path.home()),
        )
        if not output_directory:
            self._save_measurements_button.set_busy(False)
            return

        output_path = Path(output_directory) / f"{self._manifest.case_id}-measurements.pdf"
        try:
            write_measurements_pdf(output_path, self._manifest, selected_measurements)
            self._export_status_label.setText(f"Measurements saved to {output_path.parent}")
        finally:
            self._save_measurements_button.set_busy(False)

    def _export_model(self) -> None:
        self._export_model_button.set_busy(True, tint=THEME_COLORS.info)
        selected_ids = set(self._selection_state.selected_ids)
        mesh_files = collect_mesh_export_sources(
            self._manifest,
            selected_ids if selected_ids else None,
        )
        backend_summary = summary_for_manifest(self._manifest)
        try:
            output_directory = QFileDialog.getExistingDirectory(
                self,
                "Choose model export folder",
                str(Path.home()),
            )
            if not output_directory:
                return
            export_stem = (
                f"{self._manifest.case_id}-{backend_summary.export_slug}-measurement-export"
                if backend_summary is not None
                else f"{self._manifest.case_id}-measurement-export"
            )
            output_root = unique_export_destination(
                Path(output_directory) / export_stem
            )
            output_root.mkdir(parents=True, exist_ok=False)
            baseline_mesh_files = mesh_files
            if not baseline_mesh_files:
                baseline_dir = output_root / "baseline-meshes"
                baseline_dir.mkdir(parents=True, exist_ok=True)
                for vertebra in DEMO_VERTEBRAE:
                    if selected_ids and vertebra.vertebra_id not in selected_ids:
                        continue
                    destination = unique_export_destination(
                        baseline_dir / f"{vertebra.vertebra_id}.ply"
                    )
                    write_mock_box_ply(destination, vertebra)
                baseline_mesh_files = sorted(baseline_dir.glob("*.ply"), key=lambda path: path.name)

            bundle_result = export_measurement_bundle(
                output_root,
                self._manifest,
                selected_measurements=self._selected_measurements(),
                baseline_mesh_files=baseline_mesh_files,
                standing_scene_files=collect_standing_scene_sources(self._manifest),
                standing_input_assets=standing_input_assets_for_manifest(self._manifest),
                scene_models=self._scene_models,
                selected_ids=selected_ids if selected_ids else None,
                artifact_paths=collect_export_artifact_sources(self._manifest),
                backend_provenance=(
                    backend_summary.to_metadata() if backend_summary is not None else None
                ),
            )
            warning_suffix = (
                f" · {len(bundle_result.warnings)} warning(s)"
                if bundle_result.warnings
                else ""
            )
            self._export_status_label.setText(
                f"Exported measurement bundle to {bundle_result.root}{warning_suffix}"
            )
            self._refresh_mesh_details()
            self.refresh_backend_provenance()
        finally:
            self._export_model_button.set_busy(False)

    def _refresh_viewport_renders(self) -> None:
        for viewport in (self._viewport, self._front_viewport, self._side_viewport):
            plotter = getattr(viewport, "_plotter", None)
            if plotter is None:
                continue
            try:
                plotter.render()
            except Exception:
                pass
            try:
                plotter.update()
            except Exception:
                pass

    def _fit_viewports_to_scene(self) -> None:
        for viewport in (self._viewport, self._front_viewport, self._side_viewport):
            fit_scene = getattr(viewport, "fit_scene_to_reference", None)
            if callable(fit_scene):
                fit_scene()


def refresh_widget_style(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


_PRIMARY_ID_PREFERENCE = (
    "PELVIS",
    "L5", "L4", "L3", "L2", "L1",
    "T12", "T11", "T10", "T9", "T8", "T7",
    "T6", "T5", "T4", "T3", "T2", "T1",
    "C7", "C6", "C5", "C4", "C3", "C2", "C1",
    "SACRUM",
)


def default_primary_id_for_lookup(
    reference_ids: Iterable[str],
    *,
    has_model_scene: bool,
) -> str | None:
    if not has_model_scene:
        return None
    normalized_ids = {reference_id.upper() for reference_id in reference_ids if reference_id}
    for candidate in _PRIMARY_ID_PREFERENCE:
        if candidate in normalized_ids:
            return candidate
    return None


def build_initial_selection_state(
    model_ids: list[str],
    has_model_scene: bool,
    *,
    reference_ids: Iterable[str] = (),
) -> VertebraSelectionState:
    del model_ids, has_model_scene, reference_ids
    return VertebraSelectionState(
        (),
        None,
        None,
        False,
    )


def advance_selection_state(
    state: VertebraSelectionState,
    vertebra_id: str,
    *,
    remove_requested: bool,
    set_primary_requested: bool = False,
    valid_ids: set[str] | None = None,
    reference_valid_ids: set[str] | None = None,
    default_reference_id: str | None = None,
) -> VertebraSelectionState:
    valid_lookup = valid_ids if valid_ids is not None else set(VERTEBRA_INDEX)
    del set_primary_requested, reference_valid_ids, default_reference_id
    if vertebra_id not in valid_lookup:
        return state

    selected_ids = list(state.selected_ids)
    if remove_requested:
        if vertebra_id not in selected_ids:
            return state
        selected_ids.remove(vertebra_id)
        next_active = state.active_id
        if next_active == vertebra_id:
            next_active = selected_ids[-1] if selected_ids else None
        if next_active not in selected_ids:
            next_active = selected_ids[-1] if selected_ids else None
        return VertebraSelectionState(
            tuple(selected_ids),
            next_active,
            state.reference_id,
            state.isolate_selection and bool(selected_ids),
        )

    if vertebra_id not in selected_ids:
        selected_ids.append(vertebra_id)
        return VertebraSelectionState(
            tuple(selected_ids),
            vertebra_id,
            state.reference_id,
            state.isolate_selection,
        )

    return VertebraSelectionState(
        tuple(selected_ids),
        vertebra_id,
        state.reference_id,
        state.isolate_selection,
    )


def set_isolate_selection(
    state: VertebraSelectionState,
    isolate_selection: bool,
) -> VertebraSelectionState:
    return VertebraSelectionState(
        state.selected_ids,
        state.active_id,
        state.reference_id,
        isolate_selection and bool(state.selected_ids),
    )


def clear_selection_state(
    state: VertebraSelectionState,
    *,
    default_reference_id: str | None = None,
) -> VertebraSelectionState:
    next_reference_id = state.reference_id or default_reference_id
    return VertebraSelectionState((), None, next_reference_id, False)


def set_reference_state(
    state: VertebraSelectionState,
    reference_id: str,
    *,
    valid_reference_ids: set[str] | None = None,
) -> VertebraSelectionState:
    valid_lookup = valid_reference_ids if valid_reference_ids is not None else set(VERTEBRA_INDEX)
    normalized_reference_id = reference_id.upper()
    if normalized_reference_id not in valid_lookup:
        return state
    return VertebraSelectionState(
        state.selected_ids,
        state.active_id,
        normalized_reference_id,
        state.isolate_selection,
    )


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget() if item is not None else None
        child_layout = item.layout() if item is not None else None
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            clear_layout(child_layout)


def compute_relative_motion_metrics(
    active_id: str | None,
    reference_id: str | None,
    model_index: dict[str, MockVertebra] | None = None,
    standing_index: dict[str, MockVertebra] | None = None,
) -> RelativeMotionMetrics | None:
    lookup = model_index if model_index is not None else VERTEBRA_INDEX
    if active_id not in lookup or reference_id not in lookup:
        return None

    active_center = lookup[active_id].center
    reference_center = lookup[reference_id].center
    delta_x = active_center[0] - reference_center[0]
    delta_y = active_center[1] - reference_center[1]
    delta_z = active_center[2] - reference_center[2]

    if (
        standing_index is not None
        and active_id in standing_index
        and reference_id in standing_index
    ):
        standing_active = standing_index[active_id].center
        standing_reference = standing_index[reference_id].center
        delta_x = (standing_active[0] - standing_reference[0]) - delta_x
        delta_y = (standing_active[1] - standing_reference[1]) - delta_y
        delta_z = (standing_active[2] - standing_reference[2]) - delta_z

    distance = (delta_x**2 + delta_y**2 + delta_z**2) ** 0.5

    return RelativeMotionMetrics(
        active_id=active_id,
        reference_id=reference_id,
        delta_x=delta_x,
        delta_y=delta_y,
        delta_z=delta_z,
        distance=distance,
    )


def format_delta(value: float) -> str:
    return f"{value:+.2f}"


def measurement_record_label(record: MetricRecord) -> str:
    if record.label:
        return record.label
    if record.key:
        return record.key.replace("_", " ").title()
    return "Unlabeled Metric"


def measurement_record_sort_key(record: MetricRecord) -> tuple[int, str]:
    label = measurement_record_label(record)
    try:
        order = TARGET_MEASUREMENT_ORDER.index(label)
    except ValueError:
        order = len(TARGET_MEASUREMENT_ORDER)
    return (order, label)


def infer_measurement_unit(label: str, value_text: str) -> str:
    metadata = TARGET_MEASUREMENT_METADATA.get(label)
    if metadata is not None:
        return metadata[1]
    parts = value_text.strip().split()
    if len(parts) >= 2:
        return parts[-1]
    return ""


def build_manifest_measurement_record(
    label: str,
    value_text: str,
    *,
    provenance: str,
) -> MetricRecord:
    metadata = TARGET_MEASUREMENT_METADATA.get(label)
    key = metadata[0] if metadata is not None else label.strip().lower().replace(" ", "_")
    unit = infer_measurement_unit(label, value_text)
    return MetricRecord(
        metric_id=f"manifest-{key}",
        key=key,
        label=label,
        value_text=value_text,
        unit=unit,
        provenance=provenance or "manifest",
        source_stage="metrics",
        confidence=None,
    )


def measurement_records_for_manifest(manifest: CaseManifest) -> tuple[MetricRecord, ...]:
    if manifest.measurements.records:
        return tuple(sorted(manifest.measurements.records, key=measurement_record_sort_key))

    raw_values = dict(manifest.measurements.values)
    if manifest.cobb_angle and "Cobb Angle" not in raw_values:
        raw_values["Cobb Angle"] = manifest.cobb_angle
    if not raw_values:
        return ()
    return tuple(
        sorted(
            (
                build_manifest_measurement_record(
                    label,
                    value_text,
                    provenance=manifest.measurements.provenance,
                )
                for label, value_text in raw_values.items()
                if value_text
            ),
            key=measurement_record_sort_key,
        )
    )


def measurement_values_for_manifest(manifest: CaseManifest) -> dict[str, str]:
    return {
        measurement_record_label(record): record.value_text
        for record in measurement_records_for_manifest(manifest)
        if record.value_text
    }


def format_measurement_confidence(confidence: float | None) -> str:
    if confidence is None:
        return "—"
    return f"{confidence * 100:.0f}%"


def measurement_display_value(record: MetricRecord | None, fallback_text: str) -> str:
    if record is not None and record.value is not None:
        return f"{record.value:.1f}"
    value_text = record.value_text if record is not None and record.value_text else fallback_text
    if not value_text:
        return "—"
    parts = value_text.strip().split()
    return parts[0] if parts else value_text


def measurement_stage_text(record: MetricRecord) -> str:
    return record.source_stage.replace("_", " ").title() if record.source_stage else "—"


def measurement_source_text(record: MetricRecord | None, fallback_provenance: str) -> str:
    if record is None:
        return fallback_provenance or "—"
    return record.provenance or fallback_provenance or "—"


def primary_volume_for_manifest(manifest: CaseManifest) -> VolumeMetadata | None:
    ct_asset = manifest.get_asset_for_role("ct_stack")
    if ct_asset is not None:
        volume = manifest.get_volume(ct_asset.asset_id)
        if volume is not None:
            return volume
    return manifest.volumes[0] if manifest.volumes else None


def model_ids_for_manifest(manifest: CaseManifest) -> list[str]:
    return list(build_selection_model_index(models_for_manifest(manifest)))


def models_for_manifest(manifest: CaseManifest) -> list[MockVertebra]:
    mesh_models = collect_measurement_scene_models(manifest)
    if mesh_models:
        return mesh_models
    if manifest_has_measurement_scene(manifest):
        return list(DEMO_VERTEBRAE)
    return []


def manifest_has_measurement_scene(manifest: CaseManifest) -> bool:
    return bool(
        manifest.assets
        or manifest.pipeline_runs
        or manifest.patient_name
        or manifest.diagnosis
    )


def collect_measurement_scene_models(manifest: CaseManifest) -> list[MockVertebra]:
    prepared_models = collect_prepared_scene_models(manifest)
    if prepared_models:
        return prepared_models
    baseline_models: list[MockVertebra] = []
    seen: set[str] = set()
    for mesh_path in collect_mesh_export_sources(manifest):
        if not is_measurement_scene_structure_id(mesh_path.stem):
            continue
        resolved = str(mesh_path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        model = build_mesh_spec_from_path(mesh_path)
        if model is None:
            continue
        baseline_models.append(
            MockVertebra(
                vertebra_id=model.vertebra_id,
                label=model.label,
                center=model.center,
                extents=model.extents,
                mesh_path=model.mesh_path,
                selectable=is_selectable_vertebra_id(model.vertebra_id),
                pose_name="baseline",
                mesh_data=model.mesh_data,
            )
        )
    standing_models: list[MockVertebra] = []
    for scene_path in collect_standing_scene_sources(manifest):
        standing_models.extend(
            build_mesh_specs_from_glb_path(
                scene_path,
                include_structure=is_measurement_scene_structure_id,
            )
        )
    baseline_models, standing_models = normalize_measurement_pose_models(
        baseline_models,
        standing_models,
    )

    scene_models = baseline_models + standing_models
    scene_models.sort(
        key=lambda model: measurement_scene_sort_key(
            model.selection_key or model.vertebra_id,
            model.pose_name,
        )
    )
    return scene_models


def collect_prepared_scene_models(manifest: CaseManifest) -> list[MockVertebra]:
    baseline_models = load_prepared_scene_models(manifest, "prepared-scene-baseline")
    if not baseline_models:
        return []
    standing_models = load_prepared_scene_models(manifest, "prepared-scene-standing")
    baseline_models, standing_models = normalize_measurement_pose_models(
        baseline_models,
        standing_models,
    )
    scene_models = baseline_models + standing_models
    scene_models.sort(
        key=lambda model: measurement_scene_sort_key(
            model.selection_key or model.vertebra_id,
            model.pose_name,
        )
    )
    return scene_models


def load_prepared_scene_models(
    manifest: CaseManifest,
    artifact_type: str,
) -> list[MockVertebra]:
    artifact = latest_artifact_by_type(manifest, artifact_type)
    if artifact is None:
        return []
    artifact_path = Path(artifact.path)
    if not artifact_path.is_file():
        return []
    try:
        payload = read_json_artifact(artifact_path)
    except Exception:
        return []
    models_payload = payload.get("models")
    if not isinstance(models_payload, list):
        return []
    prepared_models: list[MockVertebra] = []
    for model_payload in models_payload:
        if not isinstance(model_payload, dict):
            continue
        vertebra_id = str(
            model_payload.get("selection_key")
            or model_payload.get("vertebra_id")
            or ""
        ).upper()
        mesh_path = model_payload.get("mesh_path") or ""
        center_mm = model_payload.get("center_mm")
        extents_mm = model_payload.get("extents_mm")
        if not vertebra_id:
            continue
        if not isinstance(center_mm, list) or len(center_mm) != 3:
            continue
        if not isinstance(extents_mm, list) or len(extents_mm) != 3:
            continue
        transform_matrix = coerce_transform_matrix(model_payload.get("transform_matrix"))
        prepared_models.append(
            MockVertebra(
                vertebra_id=str(model_payload.get("vertebra_id") or vertebra_id).upper(),
                label=str(model_payload.get("display_label") or vertebra_id),
                center=(
                    float(center_mm[0]),
                    float(center_mm[1]),
                    float(center_mm[2]),
                ),
                extents=(
                    float(extents_mm[0]),
                    float(extents_mm[1]),
                    float(extents_mm[2]),
                ),
                mesh_path=mesh_path,
                selectable=is_selectable_vertebra_id(vertebra_id),
                render_id=(
                    str(model_payload.get("render_id"))
                    if model_payload.get("render_id") is not None
                    else None
                ),
                selection_id=vertebra_id,
                pose_name=str(model_payload.get("pose_name") or "baseline"),
                mesh_transform=transform_matrix,
            )
        )
    return prepared_models


def latest_artifact_by_type(
    manifest: CaseManifest,
    artifact_type: str,
):
    for artifact in reversed(manifest.artifacts):
        if artifact.artifact_type == artifact_type:
            return artifact
    return None


def coerce_transform_matrix(
    payload,
) -> tuple[tuple[float, float, float, float], ...] | None:
    if not isinstance(payload, list) or len(payload) != 4:
        return None
    rows: list[tuple[float, float, float, float]] = []
    for row in payload:
        if not isinstance(row, list) or len(row) != 4:
            return None
        try:
            rows.append(
                cast(
                    tuple[float, float, float, float],
                    tuple(float(value) for value in row),
                )
            )
        except (TypeError, ValueError):
            return None
    return tuple(rows)


def is_measurement_scene_structure_id(vertebra_id: str) -> bool:
    normalized = vertebra_id.strip().upper()
    return normalized == "PELVIS" or is_selectable_vertebra_id(normalized)


def is_selectable_vertebra_id(vertebra_id: str) -> bool:
    normalized = vertebra_id.strip().upper()
    if normalized == "PELVIS":
        return True
    if len(normalized) < 2:
        return False
    prefix = normalized[0]
    suffix = normalized[1:]
    return prefix in {"C", "T", "L", "S"} and suffix.isdigit()


def measurement_scene_sort_key(
    vertebra_id: str,
    pose_name: str = "baseline",
) -> tuple[int, int, int, str]:
    normalized = vertebra_id.strip().upper()
    prefix_order = {"C": 0, "T": 1, "L": 2, "S": 3}
    pose_order = 1 if pose_name == "standing" else 0
    if normalized == "PELVIS":
        return (0, 400, pose_order, normalized)
    if is_selectable_vertebra_id(normalized):
        return (
            0,
            prefix_order[normalized[0]] * 100 + int(normalized[1:]),
            pose_order,
            normalized,
        )
    return (1, 9999, pose_order, normalized)


def build_selection_model_index(
    models: list[MockVertebra],
    *,
    pose_name: str | None = None,
    include_nonselectable: bool = False,
) -> dict[str, MockVertebra]:
    lookup: dict[str, MockVertebra] = {}
    for model in models:
        if pose_name is not None and model.pose_name != pose_name:
            continue
        selection_key = (
            model.selection_key
            if not include_nonselectable
            else (model.selection_key or model.vertebra_id)
        )
        if selection_key is None:
            continue
        lookup.setdefault(selection_key, model)
    return lookup


def build_model_lookup(
    models: list[MockVertebra],
    *,
    pose_name: str | None = None,
) -> dict[str, MockVertebra]:
    lookup: dict[str, MockVertebra] = {}
    for model in models:
        if pose_name is not None and model.pose_name != pose_name:
            continue
        lookup.setdefault(model.vertebra_id, model)
    return lookup


def align_scene_models_to_reference(
    scene_models: list[MockVertebra],
    reference_models: list[MockVertebra],
    *,
    anchor_id: str,
) -> list[MockVertebra]:
    scene_lookup = build_model_lookup(scene_models)
    reference_lookup = build_model_lookup(reference_models)
    if anchor_id not in scene_lookup or anchor_id not in reference_lookup:
        return scene_models

    scene_anchor = scene_lookup[anchor_id].center
    reference_anchor = reference_lookup[anchor_id].center
    offset = (
        reference_anchor[0] - scene_anchor[0],
        reference_anchor[1] - scene_anchor[1],
        reference_anchor[2] - scene_anchor[2],
    )

    if offset == (0.0, 0.0, 0.0):
        return scene_models

    aligned_models: list[MockVertebra] = []
    for model in scene_models:
        shifted_mesh = None
        if model.mesh_data is not None:
            shifted_mesh = model.mesh_data.copy(deep=True)
            shifted_mesh.translate(offset, inplace=True)
        aligned_models.append(
            replace(
                model,
                center=(
                    model.center[0] + offset[0],
                    model.center[1] + offset[1],
                    model.center[2] + offset[2],
                ),
                mesh_data=shifted_mesh,
            )
        )
    return aligned_models


def normalize_measurement_pose_models(
    baseline_models: list[MockVertebra],
    standing_models: list[MockVertebra],
) -> tuple[list[MockVertebra], list[MockVertebra]]:
    shared_transform = build_pelvis_world_transform(baseline_models, anchor_id="PELVIS")
    if shared_transform is None:
        shared_transform = build_pelvis_world_transform(standing_models, anchor_id="PELVIS")

    normalized_baseline = apply_group_transform(baseline_models, shared_transform)
    normalized_standing = apply_group_transform(standing_models, shared_transform)
    if normalized_baseline and normalized_standing:
        normalized_standing = align_scene_models_to_reference(
            normalized_standing,
            normalized_baseline,
            anchor_id="PELVIS",
        )
    return normalized_baseline, normalized_standing


def collect_standing_scene_sources(manifest: CaseManifest) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for asset in manifest.assets:
        if asset.kind != "mesh_3d":
            continue
        for source in (Path(asset.source_path), Path(asset.managed_path)):
            if not source.is_file() or source.suffix.lower() not in {".glb", ".gltf"}:
                continue
            resolved = str(source.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(source)
    return candidates


def standing_input_assets_for_manifest(manifest: CaseManifest) -> dict[str, Path]:
    assets: dict[str, Path] = {}
    for role, output_name in (("xray_ap", "standing_ap_input"), ("xray_lat", "standing_lat_input")):
        asset = manifest.get_asset_for_role(role)
        if asset is None:
            continue
        source_path = Path(asset.managed_path)
        if not source_path.exists() or not source_path.is_file():
            continue
        assets[output_name] = source_path
    return assets


def collect_export_artifact_sources(manifest: CaseManifest) -> dict[str, Path]:
    artifact_lookup: dict[str, Path] = {}
    artifact_types = (
        "normalized-volume",
        "segmentation",
        "point-cloud-manifest",
        "registration",
        "registration-scene",
        "measurements",
        "findings",
    )
    for artifact_type in artifact_types:
        for artifact in reversed(manifest.artifacts):
            if artifact.artifact_type != artifact_type:
                continue
            artifact_path = Path(artifact.path)
            if artifact_path.exists() and artifact_path.is_file():
                artifact_lookup[artifact_type] = artifact_path
            break
    return artifact_lookup


def collect_mesh_export_sources(
    manifest: CaseManifest,
    selected_ids: set[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    selected_lookup = {vertebra_id.upper() for vertebra_id in selected_ids or ()}

    for asset in manifest.assets:
        if asset.kind != "mesh_3d":
            continue
        for source in (Path(asset.source_path), Path(asset.managed_path)):
            if source.is_dir():
                for mesh_path in sorted(source.rglob("*.ply"), key=lambda path: path.name.lower()):
                    if selected_lookup and mesh_path.stem.upper() not in selected_lookup:
                        continue
                    resolved = str(mesh_path)
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(mesh_path)
            elif source.is_file() and source.suffix.lower() == ".ply":
                if selected_lookup and source.stem.upper() not in selected_lookup:
                    continue
                resolved = str(source)
                if resolved not in seen:
                    seen.add(resolved)
                    candidates.append(source)

    return candidates


def unique_export_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    index = 1
    while True:
        candidate = destination.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def write_mock_box_ply(output_path: Path, vertebra: MockVertebra) -> None:
    cx, cy, cz = vertebra.center
    ex, ey, ez = (extent / 2 for extent in vertebra.extents)
    vertices = [
        (cx - ex, cy - ey, cz - ez),
        (cx + ex, cy - ey, cz - ez),
        (cx + ex, cy + ey, cz - ez),
        (cx - ex, cy + ey, cz - ez),
        (cx - ex, cy - ey, cz + ez),
        (cx + ex, cy - ey, cz + ez),
        (cx + ex, cy + ey, cz + ez),
        (cx - ex, cy + ey, cz + ez),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (2, 3, 7, 6),
        (1, 2, 6, 5),
        (0, 3, 7, 4),
    ]

    lines = [
        "ply",
        "format ascii 1.0",
        f"comment SpineLab mock mesh {vertebra.vertebra_id}",
        f"element vertex {len(vertices)}",
        "property float x",
        "property float y",
        "property float z",
        f"element face {len(faces)}",
        "property list uchar int vertex_indices",
        "end_header",
    ]
    lines.extend(f"{x} {y} {z}" for x, y, z in vertices)
    lines.extend("4 " + " ".join(str(index) for index in face) for face in faces)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
