from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel

from spinelab.services import SettingsService
from spinelab.ui.theme import GEOMETRY
from spinelab.ui.widgets import PanelFrame
from spinelab.workspaces.base import WorkspacePage


def build_panel(
    title: str,
    settings: SettingsService,
    *,
    workspace_id: str,
    panel_id: str,
) -> PanelFrame:
    panel = PanelFrame(
        title,
        settings=settings,
        workspace_id=workspace_id,
        panel_id=panel_id,
    )
    panel.add_widget(QLabel(f"{title} top"), title=f"{title} Top")
    panel.add_widget(QLabel(f"{title} bottom"), title=f"{title} Bottom")
    return panel


def build_workspace(tmp_path: Path) -> WorkspacePage:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "workspace.ini"),
        QSettings.Format.IniFormat,
    )
    settings.save_shell_sidebar_visibility(True, True)
    settings.save_shell_sidebar_widths(248, 288)
    return WorkspacePage(
        "import",
        "Import",
        "Test workspace",
        settings,
        build_panel("Left", settings, workspace_id="import", panel_id="left"),
        QLabel("Center"),
        build_panel("Right", settings, workspace_id="import", panel_id="right"),
    )


def test_collapsed_right_sidebar_is_hidden_from_splitter(qtbot, tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    qtbot.addWidget(workspace)

    workspace._toggle_right()

    assert workspace._right_panel.isHidden() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._right_visible is False  # pyright: ignore[reportPrivateUsage]


def test_restored_right_sidebar_becomes_visible_again(qtbot, tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    qtbot.addWidget(workspace)

    workspace._toggle_right()
    workspace._toggle_right()

    assert workspace._right_panel.isHidden() is False  # pyright: ignore[reportPrivateUsage]
    assert workspace._right_visible is True  # pyright: ignore[reportPrivateUsage]


def test_sidebar_sections_use_vertical_splitter_with_gap(qtbot, tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    qtbot.addWidget(workspace)

    assert workspace._left_panel.section_splitter.count() == 2  # pyright: ignore[reportPrivateUsage]
    assert workspace._right_panel.section_splitter.count() == 2  # pyright: ignore[reportPrivateUsage]
    assert workspace._left_panel.section_splitter.handleWidth() == GEOMETRY.sidebar_section_gap  # pyright: ignore[reportPrivateUsage]


def test_sidebar_toggle_icons_use_opposite_header_corners(qtbot, tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    qtbot.addWidget(workspace)

    left_header = workspace._left_panel.header_row  # pyright: ignore[reportPrivateUsage]
    right_header = workspace._right_panel.header_row  # pyright: ignore[reportPrivateUsage]

    assert left_header.itemAt(left_header.count() - 1).widget() is workspace.left_toggle
    assert right_header.itemAt(0).widget() is workspace.right_toggle
    assert workspace._left_panel.title_label.isHidden() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._right_panel.title_label.isHidden() is True  # pyright: ignore[reportPrivateUsage]
    assert workspace._left_panel.outer_layout.spacing() == 0  # pyright: ignore[reportPrivateUsage]
    assert workspace._right_panel.outer_layout.spacing() == 0  # pyright: ignore[reportPrivateUsage]


def test_panel_frame_restores_saved_section_sizes(qtbot, tmp_path: Path) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "panel.ini"),
        QSettings.Format.IniFormat,
    )
    panel = build_panel("Left", settings, workspace_id="import", panel_id="left")
    qtbot.addWidget(panel)
    panel.resize(320, 480)
    panel.show()
    qtbot.wait(50)

    panel.section_splitter.setSizes([120, 280])
    panel._save_section_sizes()  # pyright: ignore[reportPrivateUsage]

    restored = build_panel("Left", settings, workspace_id="import", panel_id="left")
    qtbot.addWidget(restored)
    restored.resize(320, 480)
    restored.show()
    qtbot.wait(50)

    restored_sizes = restored.section_splitter.sizes()
    assert len(restored_sizes) == 2
    assert restored_sizes[1] > restored_sizes[0]


def test_panel_sections_use_disclosure_buttons_in_sidebar_corners(qtbot, tmp_path: Path) -> None:
    workspace = build_workspace(tmp_path)
    qtbot.addWidget(workspace)

    left_section = workspace._left_panel.section_splitter.widget(0)  # pyright: ignore[reportPrivateUsage]
    right_section = workspace._right_panel.section_splitter.widget(0)  # pyright: ignore[reportPrivateUsage]

    left_header_button = left_section.header_layout.itemAt(  # pyright: ignore[reportPrivateUsage]
        left_section.header_layout.count() - 1  # pyright: ignore[reportPrivateUsage]
    ).widget()
    right_header_button = right_section.header_layout.itemAt(0).widget()  # pyright: ignore[reportPrivateUsage]

    assert left_header_button is left_section.disclosure_button  # pyright: ignore[reportPrivateUsage]
    assert right_header_button is right_section.disclosure_button  # pyright: ignore[reportPrivateUsage]
    assert left_section.disclosure_button.text() == "⌄"  # pyright: ignore[reportPrivateUsage]

    left_section.disclosure_button.click()  # pyright: ignore[reportPrivateUsage]

    assert left_section.disclosure_button.text() == "⌃"  # pyright: ignore[reportPrivateUsage]
    assert left_section.content_widget().isHidden() is True  # pyright: ignore[reportPrivateUsage]


def test_workspace_launch_width_uses_panel_size_hints(qtbot, tmp_path: Path) -> None:
    settings = SettingsService()
    settings._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "wide-workspace.ini"),
        QSettings.Format.IniFormat,
    )
    settings.save_shell_sidebar_visibility(True, True)

    left_panel = build_panel("Left", settings, workspace_id="import", panel_id="left")
    right_panel = build_panel("Right", settings, workspace_id="import", panel_id="right")
    left_panel.add_widget(QLabel("Left sidebar width needs to fit this long launch label"))
    right_panel.add_widget(QLabel("Right sidebar width needs to fit this long launch label"))

    workspace = WorkspacePage(
        "import",
        "Import",
        "Test workspace",
        settings,
        left_panel,
        QLabel("Center"),
        right_panel,
    )
    qtbot.addWidget(workspace)
    workspace.resize(1600, 900)
    workspace.show()
    qtbot.wait(50)

    outer_sizes = workspace.outer_splitter.sizes()
    expected_width = max(left_panel.sizeHint().width(), right_panel.sizeHint().width())

    assert outer_sizes[0] >= expected_width
    assert outer_sizes[2] >= expected_width
