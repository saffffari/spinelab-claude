from pathlib import Path

from PySide6.QtCore import QSettings

from spinelab.services import SettingsService


def test_shell_sidebar_state_is_shared_across_workspaces(tmp_path: Path) -> None:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "spinelab.ini"),
        QSettings.Format.IniFormat,
    )

    service.save_shell_sidebar_widths(312, 344)
    service.save_shell_sidebar_visibility(False, True)

    assert service.load_shell_sidebar_widths() == (312, 344)
    assert service.load_shell_sidebar_visibility() == (False, True)


def test_active_segmentation_bundle_id_round_trips(tmp_path: Path) -> None:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "spinelab.ini"),
        QSettings.Format.IniFormat,
    )

    assert service.load_active_segmentation_bundle_id() is None

    service.save_active_segmentation_bundle_id("cads-skeleton")
    assert service.load_active_segmentation_bundle_id() == "cads-skeleton"

    service.clear_active_segmentation_bundle_id()
    assert service.load_active_segmentation_bundle_id() is None
