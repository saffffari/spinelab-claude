from spinelab.ui.theme import GEOMETRY, THEME_COLORS, capsule_radius
from spinelab.ui.theme.qss import build_stylesheet


def test_stylesheet_has_no_outline_strokes() -> None:
    stylesheet = build_stylesheet()

    assert "border-bottom:" not in stylesheet
    assert "border-color" not in stylesheet
    assert "outline" not in stylesheet


def test_stylesheet_uses_brighter_muted_text_tier() -> None:
    stylesheet = build_stylesheet()

    assert THEME_COLORS.text_muted == "rgba(184, 184, 184, 0.600)"
    assert THEME_COLORS.text_muted in stylesheet


def test_stylesheet_uses_transparent_background_for_inspector_preview_frame() -> None:
    stylesheet = build_stylesheet()

    assert "QFrame#InspectorPreviewFrame {" in stylesheet
    assert "background: transparent;" in stylesheet


def test_asset_tags_use_fixed_capsule_height() -> None:
    stylesheet = build_stylesheet()

    assert "QLabel#AssetTag {" in stylesheet
    assert f"min-height: {GEOMETRY.control_height_sm}px;" in stylesheet
    assert f"max-height: {GEOMETRY.control_height_sm}px;" in stylesheet
    assert f"border-radius: {capsule_radius(GEOMETRY.control_height_sm)}px;" in stylesheet


def test_stylesheet_includes_turbo_button_state_selectors() -> None:
    stylesheet = build_stylesheet()

    assert 'QPushButton#TurboModeButton[turboState="idle"] {' in stylesheet
    assert 'QPushButton#TurboModeButton[turboState="armed"],' in stylesheet
    assert 'QPushButton#TurboModeButton[turboState="active"],' in stylesheet
    assert f"background: {THEME_COLORS.viewport_overlay};" in stylesheet
    assert f"background: {THEME_COLORS.danger_soft};" in stylesheet
    assert f"background: {THEME_COLORS.danger};" in stylesheet
