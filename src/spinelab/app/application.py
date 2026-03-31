from __future__ import annotations

import sys
from typing import cast

from PySide6.QtWidgets import QApplication

from spinelab.services import configure_runtime_policy
from spinelab.ui.theme import TYPOGRAPHY, build_stylesheet


def create_application(argv: list[str] | None = None) -> QApplication:
    configure_runtime_policy()
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("SpineLab 0.2")
    app.setOrganizationName("SpineLab")
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    app.setFont(TYPOGRAPHY.create_font(13, TYPOGRAPHY.weight_regular))
    return app
