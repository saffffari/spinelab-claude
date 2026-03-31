from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spinelab.io import CaseStore
from spinelab.models import CaseManifest
from spinelab.segmentation import summary_for_active_bundle, summary_for_manifest
from spinelab.services import RenderBackendProbe, SettingsService
from spinelab.ui.svg_icons import build_svg_icon
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, TYPOGRAPHY
from spinelab.ui.widgets import (
    CapsuleButton,
    PanelFrame,
    TransparentSplitter,
    apply_text_role,
    major_button_icon_size,
)
from spinelab.visualization import SpineViewport3D, ViewportMode
from spinelab.workspaces.base import WorkspacePage
from spinelab.workspaces.measurement_workspace import (
    build_selection_model_index,
    default_primary_id_for_lookup,
    models_for_manifest,
)
from spinelab.workspaces.report_model import (
    REGION_LABELS,
    REPORT_METRIC_KEYS,
    REPORT_SECTION_IDS,
    TREND_SERIES_COLORS,
    TREND_SERIES_LABELS,
    RegionalSummaryData,
    ReportDataset,
    ReportViewState,
    build_pending_report_dataset,
    build_report_dataset_from_models,
    format_distance,
)
from spinelab.workspaces.report_widgets import (
    KpiCardWidget,
    MetricFilterChip,
    RadialSummaryWidget,
    RegionalBarChartWidget,
    TrendChartWidget,
)

SECTION_LABELS = {
    "overview": "Overview",
    "alignment": "Alignment",
    "regional": "Regional Motion",
    "vertebral": "Vertebral Detail",
    "export": "Export",
}
DETAIL_TARGET_METRICS = {
    "cervical": "Cobb Angle",
    "thoracic": "Thoracic Kyphosis",
    "lumbar": "Lumbar Lordosis",
    "pelvis": "Pelvic Tilt",
    "other": "Cobb Angle",
}
SAVE_ICON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-save-32.svg"
CSV_ICON_PATH = (
    Path(__file__).resolve().parents[1] / "ui" / "assets" / "fluent-table-simple-regular-48.svg"
)


class ReportHeroViewport(QFrame):
    selection_requested = Signal(str, bool, bool)
    camera_mode_changed = Signal(str)

    def __init__(
        self,
        models,
        *,
        interactive_3d_enabled: bool = True,
        fallback_message: str | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("PanelInner")
        self._axis_buttons: dict[str, CapsuleButton] = {}
        self._overlay: QFrame | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(0)

        overlay = QFrame()
        overlay.setObjectName("ViewportToolbar")
        self._overlay = overlay
        overlay_layout = QHBoxLayout(overlay)
        overlay_layout.setContentsMargins(
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            GEOMETRY.overlay_padding,
            0,
        )
        overlay_layout.setSpacing(GEOMETRY.overlay_gap)

        title_label = QLabel("Pose Delta Hero")
        title_label.setObjectName("ViewportOverlayChip")
        apply_text_role(title_label, "panel-title")
        overlay_layout.addWidget(title_label)
        overlay_layout.addStretch(1)

        axis_row = QHBoxLayout()
        axis_row.setContentsMargins(0, 0, 0, 0)
        axis_row.setSpacing(GEOMETRY.unit)
        for mode, label in (
            ("perspective", "3D"),
            ("front", "X"),
            ("side", "Y"),
            ("top", "Z"),
        ):
            button = CapsuleButton(label, checkable=True)
            button.setObjectName("ViewportAxisButton")
            button.setFixedHeight(GEOMETRY.control_height_sm)
            button.clicked.connect(
                lambda checked=False, selected_mode=mode: self.set_camera_mode(selected_mode)
            )
            axis_row.addWidget(button)
            self._axis_buttons[mode] = button
        overlay_layout.addLayout(axis_row)

        self._viewport = SpineViewport3D(
            "Report Hero",
            show_demo_scene=bool(models),
            models=models,
            show_toolbar=False,
            track_selection_pivot=False,
            interactive_enabled=interactive_3d_enabled,
            fallback_message=fallback_message,
        )
        self._viewport.set_reference_axes_visible(False)
        self._viewport.selection_changed.connect(
            lambda vertebra_id, remove_requested, set_primary_requested: (
                self.selection_requested.emit(
                vertebra_id,
                remove_requested,
                set_primary_requested,
                )
            )
        )
        self._viewport.camera_mode_changed.connect(self._handle_camera_mode_changed)
        layout.addWidget(overlay)
        layout.addWidget(self._viewport, stretch=1)
        self._handle_camera_mode_changed(self._viewport.current_camera_mode())

    def set_pose_delta_glyphs(self, glyphs) -> None:
        self._viewport.set_pose_delta_glyphs(glyphs)

    def set_selection(
        self,
        selected_ids: tuple[str, ...],
        *,
        active_id: str | None,
        reference_id: str | None,
    ) -> None:
        self._viewport.set_selection(
            selected_ids,
            active_id=active_id,
            reference_id=reference_id,
            isolate_selection=False,
        )

    def set_viewport_mode(self, mode: ViewportMode) -> None:
        self._viewport.set_mode(mode)

    def current_viewport_mode(self) -> ViewportMode:
        return self._viewport.current_mode()

    def set_detail_level(self, level: int) -> None:
        self._viewport.set_detail_level(level)

    def current_detail_level(self) -> int:
        return int(self._viewport.current_detail_level())

    def set_point_size(self, point_size: int) -> None:
        self._viewport.set_point_size(point_size)

    def current_point_size(self) -> int:
        return int(self._viewport.current_point_size())

    def set_pose_visibility(self, *, baseline_visible: bool, standing_visible: bool) -> None:
        self._viewport.set_pose_visibility(
            baseline_visible=baseline_visible,
            standing_visible=standing_visible,
        )

    def current_pose_visibility(self) -> tuple[bool, bool]:
        return cast(tuple[bool, bool], self._viewport.current_pose_visibility())

    def set_camera_mode(self, mode: str) -> None:
        self._viewport.set_camera_mode(mode)

    def current_camera_mode(self) -> str:
        return str(self._viewport.current_camera_mode())

    def fit_scene_to_reference(self) -> None:
        self._viewport.fit_scene_to_reference()

    def dispose(self) -> None:
        self._viewport.dispose()

    def set_render_widget_visible(self, visible: bool) -> None:
        self._viewport.set_render_widget_visible(visible)
        if visible and self._overlay is not None:
            self._overlay.raise_()

    def _handle_camera_mode_changed(self, mode: str) -> None:
        for button_mode, button in self._axis_buttons.items():
            button.setChecked(button_mode == mode)
        self.camera_mode_changed.emit(mode)


class ReportWorkspace(WorkspacePage):
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
        self._shared_viewport_mode = initial_viewport_mode
        self._shared_detail_level = initial_detail_level
        self._shared_point_size = initial_point_size
        self._shared_baseline_pose_visible = initial_baseline_pose_visible
        self._shared_standing_pose_visible = initial_standing_pose_visible
        self._shared_selected_ids = initial_selected_ids
        self._shared_active_id = initial_active_id
        self._shared_reference_id = initial_reference_id
        self._on_selection_state_changed = on_selection_state_changed
        self._shared_state_callbacks_enabled = False
        self._synchronizing_shared_state = False
        self._scene_models = models_for_manifest(manifest) if self._analysis_ready else []
        self._pending_viewport_fit = self._analysis_ready and bool(self._scene_models)
        self._reference_ids = tuple(
            build_selection_model_index(self._scene_models, include_nonselectable=True)
        )
        self._default_reference_id = default_primary_id_for_lookup(
            self._reference_ids,
            has_model_scene=bool(self._scene_models),
        )
        self._shared_reference_id = self._shared_reference_id or self._default_reference_id
        self._dataset = (
            build_report_dataset_from_models(manifest, self._scene_models)
            if self._analysis_ready
            else build_pending_report_dataset(manifest)
        )
        self._view_state = ReportViewState(
            active_metric_keys=tuple(series.key for series in self._dataset.trend_series)
            or REPORT_METRIC_KEYS
        )

        self._section_list = QListWidget()
        self._section_anchors: dict[str, QWidget] = {}
        self._metric_chips: dict[str, MetricFilterChip] = {}
        self._kpi_widgets: list[KpiCardWidget] = []
        self._pdf_export_buttons: list[CapsuleButton] = []
        self._csv_export_buttons: list[CapsuleButton] = []

        self._trend_chart = TrendChartWidget()
        self._regional_chart = RegionalBarChartWidget()
        self._radial_summary = RadialSummaryWidget()
        blocked_viewport_message = (
            render_backend.viewport_message()
            if render_backend is not None
            else "Interactive 3D disabled."
        )
        self._hero_viewport = ReportHeroViewport(
            self._scene_models,
            interactive_3d_enabled=self._interactive_3d_enabled,
            fallback_message=blocked_viewport_message,
        )
        self._notes_editor = QPlainTextEdit()
        self._notes_editor.setObjectName("ReportNotesEditor")
        self._notes_editor.setPlainText(self._dataset.notes_seed)
        self._notes_editor.setMinimumHeight(GEOMETRY.viewport_min // 2)
        self._notes_editor.setEnabled(self._analysis_ready)

        self._export_pdf_button = CapsuleButton("Export PDF", variant="primary", major=True)
        self._export_csv_button = CapsuleButton("Export CSV", major=True)
        self._configure_export_button(
            self._export_pdf_button,
            tint=THEME_COLORS.focus,
            icon_path=SAVE_ICON_PATH,
        )
        self._pdf_export_buttons.append(self._export_pdf_button)
        self._configure_export_button(
            self._export_csv_button,
            tint=THEME_COLORS.text_primary,
            icon_path=CSV_ICON_PATH,
        )
        self._csv_export_buttons.append(self._export_csv_button)
        self._export_pdf_button.setEnabled(self._analysis_ready)
        self._export_csv_button.setEnabled(self._analysis_ready)

        self._summary_title = QLabel("")
        self._summary_subtitle = QLabel("")
        self._status_summary = QLabel("")
        self._nav_summary_title = QLabel("")
        self._nav_summary_subtitle = QLabel("")
        self._nav_status_summary = QLabel("")
        self._detail_scope_value = QLabel("")
        self._detail_region_value = QLabel("")
        self._detail_target_value = QLabel("")
        self._detail_measurement_value = QLabel("")
        self._detail_pose_value = QLabel("")
        self._detail_summary_value = QLabel("")
        self._detail_source_value = QLabel("")
        self._backend_summary_value = QLabel("")
        self._export_status = QLabel("Ready" if self._analysis_ready else "Analyze required.")
        self._backend_summary_value.setWordWrap(True)
        self._export_status.setWordWrap(True)
        for label in (
            self._summary_title,
            self._summary_subtitle,
            self._status_summary,
            self._nav_summary_title,
            self._nav_summary_subtitle,
            self._nav_status_summary,
            self._detail_scope_value,
            self._detail_region_value,
            self._detail_target_value,
            self._detail_measurement_value,
            self._detail_pose_value,
            self._detail_summary_value,
            self._detail_source_value,
            self._backend_summary_value,
            self._export_status,
        ):
            label.setWordWrap(True)
        apply_text_role(self._summary_title, "workspace-title", display=True)
        apply_text_role(self._summary_subtitle, "body")
        apply_text_role(self._status_summary, "meta")
        apply_text_role(self._nav_summary_title, "body-emphasis")
        apply_text_role(self._nav_summary_subtitle, "meta")
        apply_text_role(self._nav_status_summary, "meta")
        apply_text_role(self._detail_scope_value, "body")
        apply_text_role(self._detail_region_value, "body")
        apply_text_role(self._detail_target_value, "body")
        apply_text_role(self._detail_measurement_value, "body")
        apply_text_role(self._detail_pose_value, "body")
        apply_text_role(self._detail_summary_value, "body")
        apply_text_role(self._detail_source_value, "meta")
        apply_text_role(self._backend_summary_value, "meta")
        apply_text_role(self._export_status, "meta")

        self._analytics_scroll = QScrollArea()
        self._analytics_scroll.setWidgetResizable(True)
        self._analytics_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._analytics_scroll.setWidget(self._build_analytics_canvas())

        super().__init__(
            "report",
            "Report",
            f"Case {manifest.case_id} · {manifest.patient_name}",
            settings,
            self._build_left_panel(),
            self._build_center_panel(),
            self._build_right_panel(),
        )

        self._connect_signals()
        self._apply_dataset()
        self.refresh_backend_provenance()
        self._apply_view_state()
        self._shared_state_callbacks_enabled = True

    def _configure_export_button(
        self,
        button: CapsuleButton,
        *,
        tint: str,
        icon_path: Path,
    ) -> None:
        button.setObjectName("ReportExportButton")
        button.setFixedHeight(GEOMETRY.major_button_height)
        button.setIcon(
            build_svg_icon(
                icon_path,
                major_button_icon_size(),
                device_pixel_ratio=button.devicePixelRatioF(),
                tint=tint,
            )
        )
        button.setIconSize(major_button_icon_size())

    def _build_left_panel(self) -> PanelFrame:
        panel = PanelFrame(
            "Report Sections",
            "Jump between the report narrative blocks for this Case."
            if self._analysis_ready
            else "Run Analyze in Import.",
            settings=self._workspace_settings,
            workspace_id="report",
            panel_id="left",
        )

        self._section_list.setObjectName("ReportSectionList")
        self._section_list.setSpacing(GEOMETRY.unit // 2)
        for section_id in REPORT_SECTION_IDS:
            item = QListWidgetItem(SECTION_LABELS[section_id])
            item.setData(Qt.ItemDataRole.UserRole, section_id)
            self._section_list.addItem(item)
        if self._section_list.count():
            self._section_list.setCurrentRow(0)
        self._section_list.setEnabled(self._analysis_ready)
        panel.add_widget(self._section_list, stretch=2, title="Sections")

        summary_card = QFrame()
        summary_card.setObjectName("PanelInner")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        summary_layout.setSpacing(GEOMETRY.unit // 2)
        summary_layout.addWidget(self._nav_summary_title)
        summary_layout.addWidget(self._nav_summary_subtitle)
        summary_layout.addWidget(self._nav_status_summary)
        panel.add_widget(summary_card, title="Case Summary")
        return panel

    def _build_center_panel(self) -> QWidget:
        if not self._analysis_ready:
            frame = QFrame()
            frame.setObjectName("ViewportCardFrame")
            frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return frame
        splitter = TransparentSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(GEOMETRY.viewport_gap)
        splitter.addWidget(self._analytics_scroll)
        splitter.addWidget(self._hero_viewport)
        splitter.setSizes([GEOMETRY.viewport_min * 2, GEOMETRY.viewport_min])
        return splitter

    def _build_right_panel(self) -> PanelFrame:
        placeholder = PanelFrame("Hidden")
        placeholder.hide()
        return placeholder

    def shell_sidebar_width_targets(self) -> tuple[int | None, int | None]:
        return (
            self._sidebar_target_width(  # pyright: ignore[reportPrivateUsage]
                self._left_panel,  # pyright: ignore[reportPrivateUsage]
                GEOMETRY.sidebar_min,
            ),
            None,
        )

    def sync_shell_layout(self) -> None:
        super().sync_shell_layout()
        left_width = max(
            self._saved_left_width,  # pyright: ignore[reportPrivateUsage]
            self._left_panel.minimumSizeHint().width(),  # pyright: ignore[reportPrivateUsage]
            self._left_panel.sizeHint().width(),  # pyright: ignore[reportPrivateUsage]
        )
        self._right_panel.hide()
        self.right_toggle.hide()
        self.right_reveal.hide()
        sizes = self.outer_splitter.sizes()
        if len(sizes) == 3:
            total_width = max(sum(sizes), 1)
            center_width = max(1, total_width - left_width)
            self.outer_splitter.setSizes([left_width, center_width, 0])

    def on_workspace_activated(self) -> None:
        self._hero_viewport.set_render_widget_visible(True)
        self._apply_view_state()
        if self._pending_viewport_fit and self._analysis_ready and self._scene_models:
            self._hero_viewport.fit_scene_to_reference()
            self._pending_viewport_fit = False

    def on_workspace_deactivated(self) -> None:
        self._hero_viewport.set_render_widget_visible(False)

    def dispose(self) -> None:
        self._hero_viewport.dispose()

    def _connect_signals(self) -> None:
        self._section_list.currentItemChanged.connect(self._handle_section_changed)
        self._hero_viewport.selection_requested.connect(self._handle_viewport_selection)
        self._hero_viewport.camera_mode_changed.connect(self._handle_camera_mode_changed)
        self._trend_chart.vertebra_requested.connect(self._handle_vertebra_requested)
        self._regional_chart.region_requested.connect(self._handle_region_requested)
        self._export_pdf_button.clicked.connect(self._export_pdf)
        self._export_csv_button.clicked.connect(self._export_csv)

    def _build_analytics_canvas(self) -> QWidget:
        canvas = QWidget()
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(GEOMETRY.unit * 2)

        overview_section, overview_layout = self._build_section_card(
            "overview",
            "Overview",
        )
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(GEOMETRY.unit * 2)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(GEOMETRY.unit // 2)
        title_block.addWidget(self._summary_title)
        title_block.addWidget(self._summary_subtitle)
        title_block.addWidget(self._status_summary)
        header_row.addLayout(title_block, stretch=1)

        export_header_actions = QHBoxLayout()
        export_header_actions.setContentsMargins(0, 0, 0, 0)
        export_header_actions.setSpacing(GEOMETRY.unit)
        export_header_actions.addWidget(self._export_pdf_button)
        export_header_actions.addWidget(self._export_csv_button)
        header_row.addLayout(export_header_actions)
        overview_layout.addLayout(header_row)
        canvas_layout.addWidget(overview_section)

        kpi_section, kpi_layout = self._build_section_card(
            "overview-kpis",
            "Global KPIs",
            "Alignment, sagittal balance, and total pose-delta highlights.",
        )
        kpi_grid = QGridLayout()
        kpi_grid.setContentsMargins(0, 0, 0, 0)
        kpi_grid.setHorizontalSpacing(GEOMETRY.unit * 2)
        kpi_grid.setVerticalSpacing(GEOMETRY.unit * 2)
        for index, card in enumerate(self._dataset.kpis):
            widget = KpiCardWidget(card)
            self._kpi_widgets.append(widget)
            row = index // 3
            column = index % 3
            kpi_grid.addWidget(widget, row, column)
        kpi_layout.addLayout(kpi_grid)
        canvas_layout.addWidget(kpi_section)

        dashboard_grid = QGridLayout()
        dashboard_grid.setContentsMargins(0, 0, 0, 0)
        dashboard_grid.setHorizontalSpacing(GEOMETRY.unit * 2)
        dashboard_grid.setVerticalSpacing(GEOMETRY.unit * 2)
        dashboard_grid.setColumnStretch(0, 2)
        dashboard_grid.setColumnStretch(1, 2)
        dashboard_grid.setColumnStretch(2, 1)

        alignment_section, alignment_layout = self._build_section_card(
            "alignment",
            "Alignment",
            "Vertebra-by-vertebra anatomical trend series.",
        )
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(GEOMETRY.unit)
        for metric_key in REPORT_METRIC_KEYS:
            chip = MetricFilterChip(
                metric_key,
                TREND_SERIES_LABELS[metric_key],
                TREND_SERIES_COLORS[metric_key],
            )
            chip.metric_toggled.connect(self._handle_metric_toggled)
            self._metric_chips[metric_key] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        alignment_layout.addLayout(chip_row)
        alignment_layout.addWidget(self._trend_chart)
        dashboard_grid.addWidget(alignment_section, 0, 0, 1, 2)

        regional_section, regional_layout = self._build_section_card(
            "regional",
            "Regional Motion",
            "Regional balance and contribution grouped by spine segment.",
        )
        regional_split = QHBoxLayout()
        regional_split.setContentsMargins(0, 0, 0, 0)
        regional_split.setSpacing(GEOMETRY.unit * 2)
        regional_split.addWidget(self._radial_summary, stretch=0)
        regional_split.addWidget(self._regional_chart, stretch=1)
        regional_layout.addLayout(regional_split)
        dashboard_grid.addWidget(regional_section, 1, 0, 1, 2)

        detail_section, detail_layout = self._build_section_card(
            "vertebral",
            "Vertebral Detail",
            "Linked readout for the active vertebra or region.",
        )
        detail_layout.setSpacing(GEOMETRY.unit // 2)
        detail_layout.addWidget(self._build_compact_detail_row("Scope", self._detail_scope_value))
        detail_layout.addWidget(self._build_compact_detail_row("Region", self._detail_region_value))
        detail_layout.addWidget(self._build_compact_detail_row("Target", self._detail_target_value))
        detail_layout.addWidget(
            self._build_compact_detail_row("Value", self._detail_measurement_value)
        )
        detail_layout.addWidget(self._build_compact_detail_row("Pose", self._detail_pose_value))
        detail_layout.addWidget(
            self._build_compact_detail_row("Summary", self._detail_summary_value)
        )
        detail_layout.addWidget(
            self._build_compact_detail_row("Source", self._detail_source_value)
        )
        dashboard_grid.addWidget(detail_section, 0, 2)

        export_section, export_layout = self._build_section_card(
            "export",
            "Export",
            "Notes and export actions sourced from the live report dataset.",
        )
        notes_heading = QLabel("Notes / Interpretation")
        apply_text_role(notes_heading, "section-label")
        export_layout.addWidget(notes_heading)
        export_layout.addWidget(self._notes_editor)
        export_layout.addWidget(self._backend_summary_value)
        export_layout.addWidget(self._export_status)
        footer_actions = QHBoxLayout()
        footer_actions.setContentsMargins(0, 0, 0, 0)
        footer_actions.setSpacing(GEOMETRY.unit)
        footer_pdf_button = CapsuleButton("Export PDF", variant="primary", major=True)
        self._configure_export_button(
            footer_pdf_button,
            tint=THEME_COLORS.focus,
            icon_path=SAVE_ICON_PATH,
        )
        self._pdf_export_buttons.append(footer_pdf_button)
        footer_pdf_button.clicked.connect(self._export_pdf)
        footer_actions.addWidget(footer_pdf_button)
        footer_csv_button = CapsuleButton("Export CSV", major=True)
        self._configure_export_button(
            footer_csv_button,
            tint=THEME_COLORS.text_primary,
            icon_path=CSV_ICON_PATH,
        )
        self._csv_export_buttons.append(footer_csv_button)
        footer_csv_button.clicked.connect(self._export_csv)
        footer_actions.addWidget(footer_csv_button)
        footer_actions.addStretch(1)
        export_layout.addLayout(footer_actions)
        dashboard_grid.addWidget(export_section, 1, 2)

        canvas_layout.addLayout(dashboard_grid)

        canvas_layout.addStretch(1)
        return canvas

    def _build_section_card(
        self,
        section_id: str,
        title: str,
        subtitle: str = "",
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("PanelInner")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
            GEOMETRY.panel_padding,
        )
        layout.setSpacing(GEOMETRY.unit)

        title_label = QLabel(title)
        apply_text_role(title_label, "panel-title")
        layout.addWidget(title_label)
        del subtitle
        self._section_anchors[section_id] = card
        return card, layout

    def _build_compact_detail_row(self, title: str, value_label: QLabel) -> QFrame:
        row = QFrame()
        row.setObjectName("InspectorInfoRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GEOMETRY.unit)

        title_label = QLabel(title)
        apply_text_role(title_label, "micro")
        title_label.setMinimumWidth(GEOMETRY.unit * 12)
        layout.addWidget(title_label)
        layout.addWidget(value_label, stretch=1)
        return row

    def refresh_backend_provenance(self) -> None:
        used_summary = summary_for_manifest(self._manifest)
        summary = used_summary or summary_for_active_bundle(
            self._store,
            self._workspace_settings,
        )
        if summary is None:
            self._backend_summary_value.setText("Segmentation backend · Unavailable")
            return
        source_prefix = (
            "Segmentation backend used"
            if used_summary is not None
            else "Active backend pending analyze"
        )
        self._backend_summary_value.setText(
            f"{source_prefix} · {summary.compact_label}"
        )

    def _apply_dataset(self) -> None:
        self._summary_title.setText(self._dataset.patient_name or "Untitled Case")
        self._summary_subtitle.setText(
            f"{self._dataset.diagnosis} · Case {self._dataset.case_id}"
        )
        self._nav_summary_title.setText(self._summary_title.text())
        self._nav_summary_subtitle.setText(self._summary_subtitle.text())
        if not self._analysis_ready:
            status_text = "Run Analyze in Import to unlock report data."
        elif self._dataset.has_pose_comparison:
            status_text = "Pose comparison loaded."
        elif self._dataset.has_measurements:
            status_text = "Measurements loaded."
        else:
            status_text = "Blank case."
        if self._dataset.status_lines:
            status_text = f"{status_text}\n" + "\n".join(self._dataset.status_lines)
        self._status_summary.setText(status_text)
        self._nav_status_summary.setText(status_text)

        self._trend_chart.set_chart_data(
            self._dataset.ordered_vertebrae,
            self._dataset.trend_series,
        )
        self._regional_chart.set_summaries(self._dataset.regional_summaries)
        self._radial_summary.set_summaries(self._dataset.regional_summaries)
        self._hero_viewport.set_pose_delta_glyphs(self._dataset.glyphs)
        for metric_key, chip in self._metric_chips.items():
            chip.blockSignals(True)
            chip.setChecked(metric_key in self._view_state.active_metric_keys)
            chip.blockSignals(False)

    def _apply_view_state(self) -> None:
        selected_ids = self._shared_selected_ids or self._selected_ids_for_state()
        active_id = self._shared_active_id or self._view_state.selected_vertebra_id or (
            selected_ids[0] if selected_ids else None
        )
        reference_id = self._shared_reference_id
        self._trend_chart.set_active_metric_keys(self._view_state.active_metric_keys)
        self._trend_chart.set_selected_vertebra(self._view_state.selected_vertebra_id)
        self._regional_chart.set_selected_region(self._view_state.selected_region_id)
        self._hero_viewport.set_selection(
            selected_ids,
            active_id=active_id,
            reference_id=reference_id,
        )
        if self._hero_viewport.current_viewport_mode() != self._shared_viewport_mode:
            self._hero_viewport.set_viewport_mode(self._shared_viewport_mode)
        if self._hero_viewport.current_detail_level() != self._shared_detail_level:
            self._hero_viewport.set_detail_level(self._shared_detail_level)
        if self._hero_viewport.current_point_size() != self._shared_point_size:
            self._hero_viewport.set_point_size(self._shared_point_size)
        self._hero_viewport.set_pose_visibility(
            baseline_visible=self._shared_baseline_pose_visible,
            standing_visible=self._shared_standing_pose_visible,
        )
        if self._hero_viewport.current_camera_mode() != self._view_state.viewport_axis_mode:
            self._hero_viewport.set_camera_mode(self._view_state.viewport_axis_mode)
        self._refresh_detail_panel()

    def _selected_ids_for_state(self) -> tuple[str, ...]:
        if self._view_state.selected_region_id:
            summary = self._regional_summary_lookup(self._view_state.selected_region_id)
            if summary is not None:
                return summary.vertebra_ids
        if self._view_state.selected_vertebra_id:
            return (self._view_state.selected_vertebra_id,)
        return ()

    def _regional_summary_lookup(self, region_id: str | None) -> RegionalSummaryData | None:
        if region_id is None:
            return None
        for summary in self._dataset.regional_summaries:
            if summary.region_id == region_id:
                return summary
        return None

    def _glyph_lookup(self, vertebra_id: str | None):
        if vertebra_id is None:
            return None
        for glyph in self._dataset.glyphs:
            if glyph.vertebra_id == vertebra_id:
                return glyph
        return None

    def _refresh_detail_panel(self) -> None:
        selected_vertebra_id = self._view_state.selected_vertebra_id
        selected_region_id = self._view_state.selected_region_id
        measurement_lookup = {
            record.label or record.key.replace("_", " ").title(): record
            for record in self._dataset.measurement_records
        }
        if selected_vertebra_id:
            glyph = self._glyph_lookup(selected_vertebra_id)
            region = self._regional_summary_lookup(selected_region_id)
            region_id = glyph.region_id if glyph is not None else selected_region_id or "other"
            target_label = DETAIL_TARGET_METRICS.get(region_id, "Cobb Angle")
            target_record = measurement_lookup.get(target_label)
            self._detail_scope_value.setText(f"{selected_vertebra_id} vertebra")
            self._detail_region_value.setText(
                REGION_LABELS.get(region_id, region_id.title())
            )
            self._detail_target_value.setText(target_label)
            self._detail_measurement_value.setText(
                target_record.value_text if target_record is not None else "—"
            )
            if glyph is None:
                self._detail_pose_value.setText("No pose delta")
                self._detail_summary_value.setText("No linked standing comparison payload")
            else:
                self._detail_pose_value.setText(
                    f"ΔX {glyph.delta[0]:+.1f} mm · "
                    f"ΔY {glyph.delta[1]:+.1f} mm · "
                    f"ΔZ {glyph.delta[2]:+.1f} mm"
                )
                summary_text = f"Magnitude {format_distance(glyph.magnitude)}"
                if region is not None:
                    summary_text += f" · Region total {format_distance(region.total_magnitude)}"
                self._detail_summary_value.setText(summary_text)
            self._detail_source_value.setText(
                detail_source_text(target_record, "Pose comparison")
            )
            return

        if selected_region_id:
            summary = self._regional_summary_lookup(selected_region_id)
            if summary is not None:
                target_label = DETAIL_TARGET_METRICS.get(selected_region_id, "Cobb Angle")
                target_record = measurement_lookup.get(target_label)
                self._detail_scope_value.setText(f"{summary.label} region")
                self._detail_region_value.setText(", ".join(summary.vertebra_ids))
                self._detail_target_value.setText(target_label)
                self._detail_measurement_value.setText(
                    target_record.value_text if target_record is not None else "—"
                )
                self._detail_pose_value.setText(
                    f"Avg {format_distance(summary.average_magnitude)} · "
                    f"Peak {format_distance(summary.peak_magnitude)}"
                )
                self._detail_summary_value.setText(
                    f"Total {format_distance(summary.total_magnitude)}"
                )
                self._detail_source_value.setText(
                    detail_source_text(target_record, "Regional aggregation")
                )
                return

        case_record = measurement_lookup.get("Cobb Angle")
        total_motion = sum(glyph.magnitude for glyph in self._dataset.glyphs)
        self._detail_scope_value.setText("Whole case")
        if self._dataset.dominant_region_id is not None:
            dominant = self._regional_summary_lookup(self._dataset.dominant_region_id)
            dominant_copy = dominant.label if dominant is not None else "Unknown"
        else:
            dominant_copy = "No comparison scene"
        self._detail_region_value.setText(dominant_copy)
        self._detail_target_value.setText("Cobb Angle")
        self._detail_measurement_value.setText(
            case_record.value_text if case_record is not None else self._manifest.cobb_angle or "—"
        )
        self._detail_pose_value.setText(
            format_distance(total_motion) if self._dataset.glyphs else "No pose delta"
        )
        summary_text = self._dataset.summary_text
        if self._dataset.status_lines:
            summary_text += " · " + " · ".join(self._dataset.status_lines)
        self._detail_summary_value.setText(summary_text)
        self._detail_source_value.setText(
            detail_source_text(case_record, "Case summary")
        )

    def _handle_section_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        section_id = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(section_id, str):
            return
        self._view_state = replace(self._view_state, section_id=section_id)
        target = self._section_anchors.get(section_id)
        if target is not None:
            self._analytics_scroll.ensureWidgetVisible(target, 0, GEOMETRY.unit * 2)

    def _handle_metric_toggled(self, metric_key: str, checked: bool) -> None:
        current_keys = list(self._view_state.active_metric_keys)
        if checked:
            if metric_key not in current_keys:
                current_keys.append(metric_key)
        else:
            current_keys = [key for key in current_keys if key != metric_key]
            if not current_keys:
                chip = self._metric_chips[metric_key]
                chip.blockSignals(True)
                chip.setChecked(True)
                chip.blockSignals(False)
                return
        ordered_keys = tuple(key for key in REPORT_METRIC_KEYS if key in current_keys)
        self._view_state = replace(self._view_state, active_metric_keys=ordered_keys)
        self._apply_view_state()

    def _handle_vertebra_requested(
        self,
        vertebra_id: str,
        *,
        set_primary_requested: bool = False,
    ) -> None:
        if not vertebra_id:
            self._shared_selected_ids = ()
            self._shared_active_id = None
            self._view_state = replace(
                self._view_state,
                selected_vertebra_id=None,
                selected_region_id=None,
            )
            self._apply_view_state()
            self._notify_selection_state_changed((), None, self._shared_reference_id)
            return
        region_id = None
        for summary in self._dataset.regional_summaries:
            if vertebra_id in summary.vertebra_ids:
                region_id = summary.region_id
                break
        self._shared_selected_ids = (vertebra_id,)
        self._shared_active_id = vertebra_id
        if set_primary_requested:
            self._shared_reference_id = vertebra_id
        self._view_state = replace(
            self._view_state,
            selected_vertebra_id=vertebra_id,
            selected_region_id=region_id,
        )
        self._apply_view_state()
        self._notify_selection_state_changed(
            (vertebra_id,),
            vertebra_id,
            self._shared_reference_id,
        )

    def _handle_region_requested(self, region_id: str) -> None:
        if not region_id:
            self._shared_selected_ids = ()
            self._shared_active_id = None
            self._view_state = replace(
                self._view_state,
                selected_vertebra_id=None,
                selected_region_id=None,
            )
            self._apply_view_state()
            self._notify_selection_state_changed((), None, self._shared_reference_id)
            return
        summary = self._regional_summary_lookup(region_id)
        if summary is None:
            return
        active_id = summary.vertebra_ids[0] if summary.vertebra_ids else None
        self._shared_selected_ids = summary.vertebra_ids
        self._shared_active_id = active_id
        self._view_state = replace(
            self._view_state,
            selected_region_id=region_id,
            selected_vertebra_id=None,
        )
        self._apply_view_state()
        self._notify_selection_state_changed(
            summary.vertebra_ids,
            active_id,
            self._shared_reference_id,
        )

    def _handle_viewport_selection(
        self,
        vertebra_id: str,
        _remove_requested: bool,
        set_primary_requested: bool,
    ) -> None:
        self._handle_vertebra_requested(
            vertebra_id,
            set_primary_requested=set_primary_requested,
        )

    def _handle_camera_mode_changed(self, mode: str) -> None:
        self._view_state = replace(self._view_state, viewport_axis_mode=mode)

    def apply_shared_display_state(
        self,
        *,
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
        self._apply_view_state()

    def apply_shared_selection_state(
        self,
        *,
        selected_ids: tuple[str, ...],
        active_id: str | None,
        reference_id: str | None,
        isolate_selection: bool,
    ) -> None:
        del isolate_selection
        self._synchronizing_shared_state = True
        try:
            self._shared_selected_ids = selected_ids
            self._shared_active_id = active_id
            self._shared_reference_id = (
                reference_id.upper()
                if (
                    isinstance(reference_id, str)
                    and reference_id.upper() in set(self._reference_ids)
                )
                else self._default_reference_id
            )
            self._view_state = replace(
                self._view_state,
                selected_vertebra_id=active_id,
                selected_region_id=None,
            )
            self._apply_view_state()
        finally:
            self._synchronizing_shared_state = False

    def _notify_selection_state_changed(
        self,
        selected_ids: tuple[str, ...],
        active_id: str | None,
        reference_id: str | None,
    ) -> None:
        if (
            not self._shared_state_callbacks_enabled
            or self._synchronizing_shared_state
            or self._on_selection_state_changed is None
        ):
            return
        self._on_selection_state_changed(
            selected_ids,
            active_id,
            reference_id,
            False,
        )

    def _export_pdf(self) -> None:
        for button in self._pdf_export_buttons:
            button.set_busy(True, tint=THEME_COLORS.focus)
        output_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export report PDF",
            str(Path.home() / f"{self._dataset.case_id}-report.pdf"),
            "PDF Files (*.pdf)",
        )
        if not output_path:
            for button in self._pdf_export_buttons:
                button.set_busy(False)
            return
        try:
            write_report_pdf(
                Path(output_path),
                self._manifest,
                self._dataset,
                self._notes_editor.toPlainText(),
            )
            self._export_status.setText(f"PDF exported to {Path(output_path).parent}")
        finally:
            for button in self._pdf_export_buttons:
                button.set_busy(False)

    def _export_csv(self) -> None:
        for button in self._csv_export_buttons:
            button.set_busy(True, tint=THEME_COLORS.text_primary)
        output_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export report CSV",
            str(Path.home() / f"{self._dataset.case_id}-report.csv"),
            "CSV Files (*.csv)",
        )
        if not output_path:
            for button in self._csv_export_buttons:
                button.set_busy(False)
            return
        try:
            write_report_csv(Path(output_path), self._dataset)
            self._export_status.setText(f"CSV exported to {Path(output_path).parent}")
        finally:
            for button in self._csv_export_buttons:
                button.set_busy(False)


def write_report_csv(output_path: Path, dataset: ReportDataset) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    trend_lookup = {series.key: series.values for series in dataset.trend_series}
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Case", dataset.case_id, dataset.patient_name])
        writer.writerow([])
        writer.writerow(["KPI", "Value", "Delta", "Caption"])
        for card in dataset.kpis:
            writer.writerow([card.title, card.value_text, card.delta_text, card.caption_text])

        writer.writerow([])
        writer.writerow(["Vertebra", "ΔX", "ΔY", "ΔZ", "Magnitude"])
        for index, vertebra_id in enumerate(dataset.ordered_vertebrae):
            writer.writerow(
                [
                    vertebra_id,
                    value_at(trend_lookup.get("dx"), index),
                    value_at(trend_lookup.get("dy"), index),
                    value_at(trend_lookup.get("dz"), index),
                    value_at(trend_lookup.get("magnitude"), index),
                ]
            )

        writer.writerow([])
        writer.writerow(["Region", "Average", "Peak", "Total"])
        for summary in dataset.regional_summaries:
            writer.writerow(
                [
                    summary.label,
                    f"{summary.average_magnitude:.3f}",
                    f"{summary.peak_magnitude:.3f}",
                    f"{summary.total_magnitude:.3f}",
                ]
            )


def write_report_pdf(
    output_path: Path,
    manifest: CaseManifest,
    dataset: ReportDataset,
    notes_text: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    writer.setResolution(144)
    page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
    margin = GEOMETRY.unit * 6
    y = margin

    painter = QPainter(writer)
    title_font = TYPOGRAPHY.create_font(22, TYPOGRAPHY.weight_semilight, display=True)
    subtitle_font = TYPOGRAPHY.create_font(13, TYPOGRAPHY.weight_regular)
    heading_font = TYPOGRAPHY.create_font(14, TYPOGRAPHY.weight_semilight)
    body_font = TYPOGRAPHY.create_font(12, TYPOGRAPHY.weight_regular)

    def new_page_if_needed(required_height: int) -> None:
        nonlocal y
        if y + required_height <= page_rect.height() - margin:
            return
        writer.newPage()
        y = margin

    painter.setFont(title_font)
    painter.drawText(margin, y, f"SpineLab Report · {dataset.patient_name}")
    y += GEOMETRY.unit * 5

    painter.setFont(subtitle_font)
    painter.drawText(margin, y, f"Case ID: {dataset.case_id}")
    y += GEOMETRY.unit * 3
    painter.drawText(margin, y, f"Diagnosis: {dataset.diagnosis}")
    y += GEOMETRY.unit * 3
    painter.drawText(margin, y, f"Patient ID: {manifest.patient_id or 'Unassigned'}")
    y += GEOMETRY.unit * 5

    painter.setFont(heading_font)
    painter.drawText(margin, y, "Global KPIs")
    y += GEOMETRY.unit * 4
    painter.setFont(body_font)
    for card in dataset.kpis:
        new_page_if_needed(GEOMETRY.unit * 3)
        painter.drawText(margin, y, f"{card.title}: {card.value_text} · {card.delta_text}")
        y += GEOMETRY.unit * 3

    y += GEOMETRY.unit
    painter.setFont(heading_font)
    painter.drawText(margin, y, "Regional Motion")
    y += GEOMETRY.unit * 4
    painter.setFont(body_font)
    for summary in dataset.regional_summaries:
        new_page_if_needed(GEOMETRY.unit * 3)
        painter.drawText(
            margin,
            y,
            (
                f"{summary.label}: average {format_distance(summary.average_magnitude)} · "
                f"peak {format_distance(summary.peak_magnitude)} · "
                f"total {format_distance(summary.total_magnitude)}"
            ),
        )
        y += GEOMETRY.unit * 3

    y += GEOMETRY.unit
    painter.setFont(heading_font)
    painter.drawText(margin, y, "Notes / Interpretation")
    y += GEOMETRY.unit * 4
    painter.setFont(body_font)
    notes_rect = page_rect.adjusted(margin, y, -margin, -margin)
    painter.drawText(
        notes_rect,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
        notes_text or dataset.notes_seed,
    )
    painter.end()


def detail_source_text(record, fallback: str) -> str:
    if record is None:
        return fallback
    parts: list[str] = []
    if record.source_stage:
        parts.append(record.source_stage.replace("_", " ").title())
    if record.provenance:
        parts.append(record.provenance.replace("_", " ").title())
    if record.confidence is not None:
        parts.append(f"{record.confidence * 100:.0f}% conf")
    return " · ".join(parts) if parts else fallback


def value_at(values: tuple[float, ...] | None, index: int) -> str:
    if values is None or index >= len(values):
        return ""
    return f"{values[index]:.3f}"
