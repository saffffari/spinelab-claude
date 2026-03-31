from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

import spinelab.app.main_window as main_window_module
from spinelab.app import create_application
from spinelab.io import CaseStore
from spinelab.models import CaseManifest
from spinelab.services import SettingsService


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Use the production SpineLab application bootstrap for Qt tests."""
    return create_application(["pytest"])


@pytest.fixture
def real_main_window(
    qtbot,
    monkeypatch,
    tmp_path,
) -> Callable[..., main_window_module.MainWindow]:
    """Build the real app shell for tests that need launch-truth validation."""

    def _build(
        *,
        settings: SettingsService | None = None,
        manifest: CaseManifest | None = None,
        analysis_ready: bool | None = None,
        store_root: Path | None = None,
        size: tuple[int, int] = (1600, 900),
    ) -> main_window_module.MainWindow:
        if settings is not None:
            monkeypatch.setattr(main_window_module, "SettingsService", lambda: settings)
        resolved_store_root = store_root or (tmp_path / "case-store")
        monkeypatch.setattr(
            main_window_module,
            "CaseStore",
            lambda: CaseStore(resolved_store_root),
        )
        window = main_window_module.MainWindow()
        qtbot.addWidget(window)
        if manifest is not None:
            window._manifest = manifest
            if analysis_ready is not None:
                window._analysis_ready_for_tabs = analysis_ready  # pyright: ignore[reportPrivateUsage]
            window._create_workspaces()
        window.resize(*size)
        window.show()
        qtbot.wait(50)
        return window

    return _build
