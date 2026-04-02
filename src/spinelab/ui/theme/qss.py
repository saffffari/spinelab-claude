from __future__ import annotations

from .geometry import GEOMETRY, capsule_radius, concentric_radius
from .tokens import THEME_COLORS
from .typography import TYPOGRAPHY


def build_stylesheet() -> str:
    button_radius = capsule_radius(GEOMETRY.control_height_md)
    overlay_chip_radius = capsule_radius(GEOMETRY.control_height_sm)
    panel_radius = GEOMETRY.radius_panel
    inner_radius = concentric_radius(panel_radius)
    nested_radius = concentric_radius(inner_radius)
    return f"""
QWidget {{
    background: {THEME_COLORS.shell_bg};
    color: {THEME_COLORS.text_primary};
    font-family: {TYPOGRAPHY.family_fallback};
    font-size: 13px;
}}

QWidget#WorkspacePage {{
    background: {THEME_COLORS.shell_bg};
    border: 0;
}}

QWidget#ViewportGnomon {{
    background: transparent;
    border: 0;
}}

QMainWindow {{
    background: {THEME_COLORS.shell_bg};
}}

QFrame#SurfaceFrame {{
    background: transparent;
    border: 0;
    border-radius: 0;
}}

QFrame#PanelFrame {{
    background: {THEME_COLORS.panel_bg};
    border: 1px solid {THEME_COLORS.border_soft};
    border-radius: {panel_radius}px;
}}

QFrame#PanelInner {{
    background: transparent;
    border: 0;
    border-radius: {inner_radius}px;
}}

QFrame#NestedPanelInner {{
    background: transparent;
    border: 0;
    border-radius: {nested_radius}px;
}}

QFrame#PanelSectionHost {{
    background: transparent;
    border: 0;
}}

QFrame#InspectorInfoGrid {{
    background: transparent;
    border: 0;
}}

QWidget#PanelSectionHeader,
QFrame[embeddedSectionBody="true"],
QFrame#PanelInner[embeddedSectionBody="true"],
QFrame#InspectorPreviewFrame[embeddedSectionBody="true"],
QFrame#InspectorActionCard[embeddedSectionBody="true"],
QFrame#InspectorSummaryCard[embeddedSectionBody="true"],
QFrame#ManualMeasurementToolbar[embeddedSectionBody="true"] {{
    background: transparent;
    border: 0;
    border-radius: 0;
}}

QFrame#ViewportToolbar {{
    background: transparent;
    border: 0;
}}

QFrame#ImportViewportToolbar,
QFrame#ManualMeasurementToolbar {{
    background: {THEME_COLORS.panel_bg};
    border: 0;
    border-radius: {nested_radius}px;
}}

QFrame#ViewportOverlayBar,
QFrame#ViewportOverlayFooter {{
    background: transparent;
    border: 0;
}}

QFrame#ViewportOverlayGroup {{
    background: transparent;
    border: 0;
    border-radius: {button_radius}px;
}}

QFrame#CenterToolbarGroup {{
    background: transparent;
    border: 0;
    border-radius: {button_radius}px;
}}

QLabel#ViewportOverlayChip,
QLabel#ViewportOverlayStatus,
QLabel#ViewportOverlayHint {{
    background: {THEME_COLORS.viewport_overlay};
    border: 0;
    border-radius: {overlay_chip_radius}px;
    min-height: {GEOMETRY.control_height_sm}px;
    padding: 0 {GEOMETRY.unit * 2}px;
}}

QFrame#ViewportFallback,
QFrame#ViewportCardFrame {{
    background: {THEME_COLORS.viewport_bg};
    border: 0;
    border-radius: {inner_radius}px;
}}

QFrame#PendingAnalysisViewport {{
    background: transparent;
    border: 0;
}}

QFrame#ImageViewportCanvas {{
    background: {THEME_COLORS.viewport_bg};
    border: 0;
    border-radius: {nested_radius}px;
}}

QLabel#ImageViewportLabel {{
    background: {THEME_COLORS.viewport_bg};
    border: 0;
    border-radius: {nested_radius}px;
}}

QFrame#HeaderBar {{
    background: {THEME_COLORS.shell_elevated};
    border: 0;
}}

QFrame#HeaderStatusStrip {{
    background: transparent;
    border: 0;
}}

QLabel#HeaderStatusLabel {{
    color: {THEME_COLORS.text_muted};
}}

QPushButton#HeaderRendererButton {{
    min-height: {GEOMETRY.header_control_height}px;
    padding-left: {GEOMETRY.unit * 2}px;
    padding-right: {GEOMETRY.unit * 2}px;
}}

QPushButton#TurboModeButton,
QPushButton#InspectorAnalyzeButton {{
    background: transparent;
    border: 0;
}}

QToolButton#HeaderMinimizeButton,
QToolButton#HeaderMaximizeButton,
QToolButton#HeaderCloseButton {{
    min-width: {GEOMETRY.header_control_height + GEOMETRY.unit}px;
    max-width: {GEOMETRY.header_control_height + GEOMETRY.unit}px;
    min-height: {GEOMETRY.header_control_height}px;
    max-height: {GEOMETRY.header_control_height}px;
    padding: 0;
    border-radius: {concentric_radius(inner_radius)}px;
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QToolButton#HeaderMinimizeButton:hover,
QToolButton#HeaderMaximizeButton:hover {{
    background: {THEME_COLORS.panel_inner_bg};
    color: {THEME_COLORS.text_primary};
}}

QToolButton#HeaderCloseButton:hover {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
}}

QFrame#FooterBar {{
    background: {THEME_COLORS.shell_elevated};
    border: 0;
}}

QLabel#FooterStatusLabel {{
    color: {THEME_COLORS.text_muted};
}}

QLabel#FooterRendererLabel {{
    color: {THEME_COLORS.text_muted};
}}

QLabel#FooterRendererLabel[renderState="ok"] {{
    color: {THEME_COLORS.success};
}}

QLabel#FooterRendererLabel[renderState="blocked"] {{
    color: {THEME_COLORS.warning};
}}

QLabel#FooterRendererLabel[renderState="unknown"] {{
    color: {THEME_COLORS.warning};
}}

QLabel#FooterRendererLabel[renderState="inactive"] {{
    color: {THEME_COLORS.text_muted};
}}

QLabel {{
    background: transparent;
}}

QLabel[role="workspace-title"] {{
    font-size: 20px;
}}

QLabel[role="panel-title"] {{
    font-size: 15px;
}}

QFrame#PanelFrame QLabel[role="panel-title"],
QFrame#SurfaceFrame QLabel[role="panel-title"] {{
    color: {THEME_COLORS.text_primary};
}}

QFrame#PanelInner QLabel[role="panel-title"],
QFrame#PanelInner QLabel[role="body-emphasis"],
QFrame#PanelInner QLabel[role="body"] {{
    color: {THEME_COLORS.text_primary};
}}

QLabel[role="header-meta"] {{
    font-size: 13px;
    color: {THEME_COLORS.text_muted};
}}

QLabel[role="section-label"] {{
    font-size: 12px;
    color: {THEME_COLORS.text_secondary};
}}

QLabel[role="meta"] {{
    font-size: 12px;
    color: {THEME_COLORS.text_muted};
}}

QFrame#InspectorActionCard QLabel[role="panel-title"],
QFrame#InspectorSummaryCard QLabel[role="panel-title"],
QFrame#InspectorInfoGrid QLabel[role="panel-title"],
QFrame#InspectorActionCard QLabel[role="body-emphasis"],
QFrame#InspectorSummaryCard QLabel[role="body-emphasis"],
QFrame#InspectorInfoGrid QLabel[role="body-emphasis"] {{
    color: {THEME_COLORS.text_secondary};
}}

QFrame#InspectorActionCard QLabel[role="body"],
QFrame#InspectorSummaryCard QLabel[role="body"],
QFrame#InspectorInfoGrid QLabel[role="body"] {{
    color: {THEME_COLORS.text_muted};
}}

QPushButton,
QToolButton {{
    min-height: {GEOMETRY.control_height_md}px;
    padding: 0 {GEOMETRY.unit * 2}px;
    border-radius: {button_radius}px;
    border: 0;
    background: transparent;
}}

QPushButton:hover,
QToolButton:hover {{
    background: {THEME_COLORS.viewport_overlay};
}}

QPushButton#HeaderWorkspaceTabButton {{
    padding-left: {GEOMETRY.unit * 2}px;
    padding-right: {GEOMETRY.unit * 2}px;
    border-top-left-radius: {button_radius}px;
    border-top-right-radius: {button_radius}px;
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
    background: transparent;
}}

QPushButton#HeaderWorkspaceTabButton:hover {{
    background: {THEME_COLORS.viewport_overlay};
}}

QPushButton#HeaderWorkspaceTabButton:checked,
QPushButton#HeaderWorkspaceTabButton:checked:hover {{
    background: {THEME_COLORS.panel_inner_bg};
    color: {THEME_COLORS.focus};
}}

QToolButton#HeaderMenuButton::menu-indicator {{
    image: none;
    width: 0px;
}}

QPushButton[majorButton="true"] {{
    min-height: {GEOMETRY.major_button_height}px;
    background: transparent;
    border: 1px solid {THEME_COLORS.border_soft};
    color: {THEME_COLORS.text_primary};
    text-align: left;
    padding-left: {GEOMETRY.unit * 2}px;
    padding-right: {GEOMETRY.unit * 2}px;
}}

QPushButton[variant="primary"],
QToolButton[variant="primary"] {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.focus};
}}

QPushButton[variant="info"],
QToolButton[variant="info"] {{
    background: {THEME_COLORS.info_soft};
    color: {THEME_COLORS.info};
}}

QPushButton[variant="success"] {{
    background: {THEME_COLORS.success_soft};
    color: {THEME_COLORS.success};
}}

QPushButton[variant="warning"] {{
    background: {THEME_COLORS.warning_soft};
    color: {THEME_COLORS.warning};
}}

QPushButton[variant="danger"] {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
}}

QPushButton[majorButton="true"]:disabled {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_muted};
}}

QPushButton#VertebraSelectionButton[selectionState="idle"] {{
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QPushButton#VertebraSelectionButton {{
    padding-left: {GEOMETRY.unit}px;
    padding-right: {GEOMETRY.unit}px;
}}

QPushButton#VertebraSelectionButton[selectionState="selected"] {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.focus};
}}

QPushButton#VertebraSelectionButton[selectionState="reference"] {{
    background: {THEME_COLORS.focus_reference_soft};
    color: {THEME_COLORS.focus_reference};
}}

QPushButton:checked,
QToolButton:checked {{
    background: {THEME_COLORS.focus_soft};
    border: 0;
    color: {THEME_COLORS.focus};
}}

QPushButton#PoseVisibilityButton[visibilityState="shown"] {{
    background: {THEME_COLORS.info_soft};
    color: {THEME_COLORS.info};
}}

QPushButton#PoseVisibilityButton[visibilityState="hidden"] {{
    background: {THEME_COLORS.warning_strong_soft};
    color: {THEME_COLORS.warning_strong};
}}

QPushButton#PoseVisibilityButton:disabled {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_muted};
}}

QPushButton#MeasurementActionButton[actionState="empty"] {{
    background: {THEME_COLORS.warning_strong_soft};
    color: {THEME_COLORS.warning_strong};
}}

QPushButton#MeasurementActionButton[actionState="ready"] {{
    background: {THEME_COLORS.info_soft};
    color: {THEME_COLORS.info};
}}

QPushButton#MeasurementActionButton:checked {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.focus};
}}

QPushButton#MeasurementActionButton:disabled {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_muted};
}}

QToolButton#SidebarToggleButton {{
    min-height: 0;
    max-height: 20px;
    min-width: 0;
    max-width: 20px;
    padding: 0;
    border: 0;
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QToolButton#SidebarToggleButton:hover {{
    border: 0;
    color: {THEME_COLORS.focus};
}}

QToolButton#PanelSectionDisclosureButton {{
    min-height: 0;
    max-height: 20px;
    min-width: 0;
    max-width: 20px;
    padding: 0;
    border: 0;
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QToolButton#PanelSectionDisclosureButton:hover {{
    border: 0;
    color: {THEME_COLORS.focus};
}}

QPushButton#ViewportModeButton,
QPushButton#ViewportAxisButton {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_secondary};
}}

QPushButton#ViewportModeButton:hover,
QPushButton#ViewportAxisButton:hover {{
    background: {THEME_COLORS.viewport_overlay};
}}

QPushButton#ViewportModeButton {{
    min-width: {GEOMETRY.toolbar_control_size}px;
    max-width: {GEOMETRY.toolbar_control_size}px;
    min-height: {GEOMETRY.toolbar_control_size}px;
    max-height: {GEOMETRY.toolbar_control_size}px;
    padding: 0;
    border-radius: {capsule_radius(GEOMETRY.toolbar_control_size)}px;
}}

QPushButton#ViewportAxisButton {{
    min-height: {GEOMETRY.toolbar_control_size}px;
    max-height: {GEOMETRY.toolbar_control_size}px;
    padding: 0;
    border-radius: {capsule_radius(GEOMETRY.toolbar_control_size)}px;
}}

QPushButton#ViewportModeButton:disabled,
QPushButton#ViewportAxisButton:disabled {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_muted};
}}

QToolButton#ManualMeasurementToolButton {{
    min-width: {GEOMETRY.toolbar_control_size}px;
    max-width: {GEOMETRY.toolbar_control_size}px;
    min-height: {GEOMETRY.toolbar_control_size}px;
    max-height: {GEOMETRY.toolbar_control_size}px;
    padding: 0;
    border: 0;
    border-radius: {capsule_radius(GEOMETRY.toolbar_control_size)}px;
    background: {THEME_COLORS.viewport_overlay};
}}

QToolButton#ManualMeasurementToolButton:hover {{
    background: {THEME_COLORS.viewport_overlay};
}}

QToolButton#ManualMeasurementToolButton:checked {{
    background: {THEME_COLORS.focus_soft};
}}

QLineEdit,
QTextEdit,
QPlainTextEdit {{
    background: {THEME_COLORS.viewport_overlay};
    border: 0;
    border-radius: {inner_radius}px;
    padding: 0 {GEOMETRY.unit * 2}px;
}}

QListWidget {{
    background: transparent;
    border: 0;
    border-radius: {inner_radius}px;
    padding: 0 {GEOMETRY.unit}px;
}}

QTreeWidget {{
    background: transparent;
    border: 0;
    border-radius: {inner_radius}px;
    padding: 0;
}}

QToolButton#MeasurementCheckButton {{
    min-height: {GEOMETRY.control_height_sm - 8}px;
    min-width: {GEOMETRY.control_height_sm - 8}px;
    max-height: {GEOMETRY.control_height_sm - 8}px;
    max-width: {GEOMETRY.control_height_sm - 8}px;
    padding: 0;
    border: 0;
    border-radius: {capsule_radius(GEOMETRY.control_height_sm - 8)}px;
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QToolButton#MeasurementCheckButton:hover {{
    background: transparent;
}}

QToolButton#MeasurementCheckButton:checked {{
    color: {THEME_COLORS.focus};
}}

QListWidget::item {{
    padding: {GEOMETRY.unit}px;
    border-radius: {concentric_radius(inner_radius)}px;
}}

QTreeWidget::item {{
    padding: {GEOMETRY.unit}px;
    border-radius: {concentric_radius(inner_radius)}px;
}}

QListWidget::item:selected {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.text_primary};
}}

QTreeWidget::item:selected {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.text_primary};
}}

QTreeWidget#CaseExplorerTree::item:selected,
QTreeWidget#CaseExplorerTree::branch:selected {{
    background: transparent;
    color: {THEME_COLORS.text_primary};
}}

QTreeWidget#MeasurementTree::item:selected,
QTreeWidget#MeasurementTree::branch:selected {{
    background: transparent;
    color: {THEME_COLORS.text_primary};
}}

QPushButton#ImportDropZone {{
    border-radius: {inner_radius}px;
    min-height: {GEOMETRY.major_button_height}px;
}}

QPushButton#ImportDropZone:hover {{
    background: {THEME_COLORS.info_soft};
}}

QFrame#AssetRow {{
    background: {THEME_COLORS.viewport_overlay};
    border: 0;
    border-radius: {inner_radius}px;
}}

QWidget#AssetMetaPanel,
QWidget#AssetActionSlot {{
    background: transparent;
    border: 0;
}}

QFrame#AssetPreview,
QFrame#InspectorPreviewImage {{
    background: transparent;
    border: 0;
}}

QFrame#InspectorPreviewFrame {{
    background: {THEME_COLORS.viewport_empty_bg};
    border: 0;
    border-radius: {inner_radius}px;
}}

QToolButton#AssetDeleteButton {{
    min-height: {GEOMETRY.control_height_md}px;
    min-width: {GEOMETRY.control_height_md}px;
    max-height: {GEOMETRY.control_height_md}px;
    max-width: {GEOMETRY.control_height_md}px;
    padding: 0;
    border: 0;
    border-radius: {capsule_radius(GEOMETRY.control_height_md)}px;
    background: transparent;
}}

QToolButton#AssetDeleteButton:hover {{
    background: {THEME_COLORS.danger_soft};
}}

QToolButton#AssetDeleteButton:disabled {{
    opacity: 0.4;
}}

QFrame#InspectorActionCard {{
    background: transparent;
    border: 0;
}}

QFrame#InspectorSummaryCard {{
    background: {THEME_COLORS.viewport_overlay};
    border: 0;
    border-radius: {inner_radius}px;
}}

QFrame#InspectorSummaryCard[variant="success"] {{
    background: {THEME_COLORS.success_soft};
}}

QFrame#InspectorSummaryCard[variant="success"] QLabel {{
    color: {THEME_COLORS.success};
}}

QFrame#InspectorSummaryCard[variant="success"] QLabel#InspectorSummaryKicker,
QFrame#InspectorSummaryCard[variant="success"] QLabel#InspectorSummaryChevron {{
    color: {THEME_COLORS.success};
}}

QFrame#InspectorInfoRow {{
    background: transparent;
    border: 0;
}}

QLabel#InspectorSummaryKicker {{
    color: {THEME_COLORS.text_muted};
}}

QLabel#InspectorSummaryChevron,
QLabel#InspectorInfoIcon {{
    color: {THEME_COLORS.text_muted};
    background: transparent;
}}

QLabel#InspectorEmptyBubble {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
    padding: 0;
    border: 0;
    border-radius: {capsule_radius(GEOMETRY.control_height_sm)}px;
}}

QLabel#PendingAnalysisMessage {{
    background: transparent;
    color: {THEME_COLORS.danger};
}}

QLabel#PendingAnalysisHint {{
    background: transparent;
    color: {THEME_COLORS.text_secondary};
}}

QPushButton#InspectorAnalyzeButton {{
    background: {THEME_COLORS.info_soft};
    color: {THEME_COLORS.info};
}}

QPushButton#InspectorAnalyzeButton:hover {{
    background: {THEME_COLORS.info_soft};
}}

QWidget#PoseEngineSelectorStrip,
QWidget#ComparisonSelectorHost {{
    background: transparent;
    border: 0;
}}

QPushButton#TurboModeButton[turboState="idle"] {{
    background: {THEME_COLORS.viewport_overlay};
    color: {THEME_COLORS.text_primary};
}}

QPushButton#TurboModeButton[turboState="idle"]:hover {{
    background: {THEME_COLORS.panel_inner_bg};
    color: {THEME_COLORS.text_primary};
}}

QPushButton#TurboModeButton[turboState="armed"],
QPushButton#TurboModeButton[turboState="armed"]:hover {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
}}

QPushButton#TurboModeButton[turboState="active"],
QPushButton#TurboModeButton[turboState="active"]:hover,
QPushButton#TurboModeButton[turboState="active"]:disabled {{
    background: {THEME_COLORS.danger};
    color: {THEME_COLORS.text_primary};
}}

QPushButton#ComparisonSelectorButton {{
    background: {THEME_COLORS.viewport_overlay};
}}

QPushButton#ComparisonSelectorButton[variant="danger"],
QPushButton#ComparisonSelectorButton[variant="danger"]:hover {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
}}

QPushButton#ComparisonSelectorButton[variant="success"],
QPushButton#ComparisonSelectorButton[variant="success"]:hover {{
    background: {THEME_COLORS.success_soft};
    color: {THEME_COLORS.success};
}}

QLabel#AssetTag {{
    min-height: {GEOMETRY.control_height_sm}px;
    max-height: {GEOMETRY.control_height_sm}px;
    padding: 0 {GEOMETRY.unit * 2}px;
    border: 0;
    border-radius: {capsule_radius(GEOMETRY.control_height_sm)}px;
}}

QLabel#AssetTag[variant="xray"] {{
    background: {THEME_COLORS.warning_strong_soft};
    color: {THEME_COLORS.warning_strong};
}}

QLabel#AssetTag[variant="ct"] {{
    background: {THEME_COLORS.danger_soft};
    color: {THEME_COLORS.danger};
}}

QLabel#AssetTag[variant="mri"] {{
    background: {THEME_COLORS.info_soft};
    color: {THEME_COLORS.info};
}}

QLabel#AssetTag[variant="model"] {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.focus};
}}

QScrollBar:vertical,
QScrollBar:horizontal {{
    background: {THEME_COLORS.scrollbar_track};
    border: 0;
    margin: 0;
}}

QScrollBar:vertical {{
    width: 8px;
}}

QScrollBar:horizontal {{
    height: 8px;
}}

QScrollBar::handle:vertical,
QScrollBar::handle:horizontal {{
    background: {THEME_COLORS.scrollbar_thumb};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::add-line,
QScrollBar::sub-line,
QScrollBar::add-page,
QScrollBar::sub-page {{
    border: 0;
    background: transparent;
}}

QSlider#ViewportSliceSlider {{
    background: transparent;
    min-height: {GEOMETRY.control_height_sm}px;
}}

QSlider#ViewportSliceSlider::groove:horizontal {{
    background: {THEME_COLORS.panel_inner_bg};
    height: 6px;
    border-radius: 3px;
}}

QSlider#ViewportSliceSlider::sub-page:horizontal {{
    background: {THEME_COLORS.focus_soft};
    border-radius: 3px;
}}

QSlider#ViewportSliceSlider::add-page:horizontal {{
    background: {THEME_COLORS.panel_inner_bg};
    border-radius: 3px;
}}

QSlider#ViewportSliceSlider::handle:horizontal {{
    background: {THEME_COLORS.focus};
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}

QSplitter::handle {{
    background: transparent;
}}

QMenu {{
    background: {THEME_COLORS.panel_bg};
    border: 0;
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 20px;
    border-radius: 10px;
}}

QMenu::item:selected {{
    background: {THEME_COLORS.focus_soft};
    color: {THEME_COLORS.text_primary};
}}
"""
