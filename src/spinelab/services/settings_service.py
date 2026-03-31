from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings


class SettingsService:
    def __init__(
        self,
        organization: str = "SpineLab",
        application: str = "SpineLab0.2",
    ) -> None:
        self._settings = QSettings(organization, application)

    def save_window_geometry(self, geometry: QByteArray) -> None:
        self._settings.setValue("window/geometry", geometry)

    def load_window_geometry(self) -> QByteArray | None:
        value = self._settings.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    def save_current_workspace(self, workspace_id: str) -> None:
        self._settings.setValue("window/current_workspace", workspace_id)

    def load_current_workspace(self) -> str | None:
        value = self._settings.value("window/current_workspace")
        return value if isinstance(value, str) else None

    def save_shell_sidebar_widths(self, left_width: int, right_width: int) -> None:
        self._settings.setValue("shell/sidebar_widths/left", left_width)
        self._settings.setValue("shell/sidebar_widths/right", right_width)

    def load_shell_sidebar_widths(self) -> tuple[int | None, int | None]:
        left_value = self._settings.value("shell/sidebar_widths/left")
        right_value = self._settings.value("shell/sidebar_widths/right")
        left_width = int(left_value) if left_value is not None else None
        right_width = int(right_value) if right_value is not None else None
        return left_width, right_width

    def save_shell_sidebar_visibility(self, left_visible: bool, right_visible: bool) -> None:
        self._settings.setValue("shell/sidebar_visibility/left", left_visible)
        self._settings.setValue("shell/sidebar_visibility/right", right_visible)

    def load_shell_sidebar_visibility(
        self,
        default_left: bool = True,
        default_right: bool = True,
    ) -> tuple[bool, bool]:
        left_value = self._settings.value("shell/sidebar_visibility/left")
        right_value = self._settings.value("shell/sidebar_visibility/right")
        left_visible = default_left if left_value is None else str(left_value).lower() == "true"
        right_visible = (
            default_right if right_value is None else str(right_value).lower() == "true"
        )
        return left_visible, right_visible

    def save_splitter_state(self, workspace_id: str, name: str, state: QByteArray) -> None:
        self._settings.setValue(f"workspace/{workspace_id}/splitter/{name}", state)

    def load_splitter_state(self, workspace_id: str, name: str) -> QByteArray | None:
        value = self._settings.value(f"workspace/{workspace_id}/splitter/{name}")
        return value if isinstance(value, QByteArray) else None

    def save_sizes(self, workspace_id: str, name: str, sizes: Iterable[int]) -> None:
        self._settings.setValue(f"workspace/{workspace_id}/sizes/{name}", list(sizes))

    def load_sizes(self, workspace_id: str, name: str) -> list[int] | None:
        value = self._settings.value(f"workspace/{workspace_id}/sizes/{name}")
        if isinstance(value, list):
            return [int(item) for item in value]
        return None

    def save_flag(self, workspace_id: str, name: str, value: bool) -> None:
        self._settings.setValue(f"workspace/{workspace_id}/flags/{name}", value)

    def load_flag(self, workspace_id: str, name: str, default: bool = True) -> bool:
        value = self._settings.value(f"workspace/{workspace_id}/flags/{name}")
        return default if value is None else str(value).lower() == "true"

    def save_active_segmentation_bundle_id(self, bundle_id: str) -> None:
        self._settings.setValue("segmentation/active_bundle_id", bundle_id)

    def load_active_segmentation_bundle_id(self) -> str | None:
        value = self._settings.value("segmentation/active_bundle_id")
        return value if isinstance(value, str) and value.strip() else None

    def clear_active_segmentation_bundle_id(self) -> None:
        self._settings.remove("segmentation/active_bundle_id")

    def save_performance_mode(self, mode: str) -> None:
        self._settings.setValue("performance/mode", str(mode).strip().lower())

    def load_performance_mode(self) -> str | None:
        value = self._settings.value("performance/mode")
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        return normalized or None

    def load_recent_case_paths(self) -> list[Path]:
        value = self._settings.value("cases/recent_paths")
        if not isinstance(value, list):
            return []
        return [Path(str(item)) for item in value if str(item).strip()]

    def save_recent_case_paths(self, paths: Iterable[Path | str]) -> None:
        normalized = [str(Path(path)) for path in paths if str(path).strip()]
        self._settings.setValue("cases/recent_paths", normalized)

    def add_recent_case_path(self, path: Path | str, *, limit: int = 20) -> None:
        normalized = str(Path(path))
        existing = [str(item) for item in self.load_recent_case_paths()]
        deduped = [normalized, *[item for item in existing if item != normalized]]
        self.save_recent_case_paths(deduped[:limit])

    def remove_recent_case_path(self, path: Path | str) -> None:
        normalized = str(Path(path))
        retained = [item for item in self.load_recent_case_paths() if str(item) != normalized]
        self.save_recent_case_paths(retained)

    def save_last_case_directory(self, path: Path | str) -> None:
        self._settings.setValue("cases/last_directory", str(Path(path)))

    def load_last_case_directory(self) -> Path | None:
        value = self._settings.value("cases/last_directory")
        if not isinstance(value, str) or not value.strip():
            return None
        return Path(value)
