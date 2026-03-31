"""Reusable UI widgets."""

from .chrome import (
    CapsuleButton,
    CollapsiblePanelSection,
    CornerIconButton,
    FooterStatusBar,
    HeaderStatusStrip,
    MenuButton,
    NestedBubbleFrame,
    PanelFrame,
    ViewportCard,
    apply_text_role,
    major_button_icon_size,
)
from .performance import AnalyzeProgressButton, TurboModeButton
from .splitters import TransparentSplitter, schedule_splitter_midpoint

__all__ = [
    "AnalyzeProgressButton",
    "CapsuleButton",
    "CollapsiblePanelSection",
    "CornerIconButton",
    "FooterStatusBar",
    "HeaderStatusStrip",
    "MenuButton",
    "NestedBubbleFrame",
    "PanelFrame",
    "TurboModeButton",
    "TransparentSplitter",
    "ViewportCard",
    "apply_text_role",
    "major_button_icon_size",
    "schedule_splitter_midpoint",
]
