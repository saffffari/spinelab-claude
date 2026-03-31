from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer

from spinelab.app import create_application
from spinelab.services import configure_runtime_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch SpineLab 0.2")
    parser.add_argument("--smoke-test", action="store_true", help="Launch and exit quickly")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_runtime_policy()
    from spinelab.app import MainWindow

    app = create_application(sys.argv if argv is None else argv)
    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(250, app.quit)
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
