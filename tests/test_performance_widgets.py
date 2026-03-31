from PySide6.QtCore import Qt

from spinelab.services.performance import PerformanceMode
from spinelab.ui.theme import GEOMETRY
from spinelab.ui.widgets import AnalyzeProgressButton, TurboModeButton


def test_turbo_mode_button_first_click_only_arms(qtbot) -> None:
    button = TurboModeButton()
    emitted: list[str] = []
    button.show()
    qtbot.addWidget(button)
    button.mode_changed.connect(emitted.append)

    assert button.state() == "idle"
    assert button.text() == "Arm Turbo"

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.mode() == PerformanceMode.ADAPTIVE
    assert button.state() == "armed"
    assert emitted == []


def test_turbo_mode_button_armed_state_times_out(qtbot) -> None:
    button = TurboModeButton()
    button.show()
    qtbot.addWidget(button)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: button.state() == "idle", timeout=2500)

    assert button.mode() == PerformanceMode.ADAPTIVE
    assert button.is_armed() is False


def test_turbo_mode_button_second_click_activates_turbo(qtbot) -> None:
    button = TurboModeButton()
    emitted: list[str] = []
    button.show()
    qtbot.addWidget(button)
    button.mode_changed.connect(emitted.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.mode() == PerformanceMode.TURBO
    assert button.state() == "active"
    assert emitted == ["turbo"]


def test_turbo_mode_button_active_click_restores_adaptive(qtbot) -> None:
    button = TurboModeButton(PerformanceMode.TURBO)
    emitted: list[str] = []
    button.show()
    qtbot.addWidget(button)
    button.mode_changed.connect(emitted.append)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert button.mode() == PerformanceMode.ADAPTIVE
    assert button.state() == "idle"
    assert emitted == ["adaptive"]


def test_turbo_mode_button_external_mode_sync_cancels_armed_state(qtbot) -> None:
    button = TurboModeButton()
    button.show()
    qtbot.addWidget(button)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
    assert button.state() == "armed"

    button.set_mode(PerformanceMode.TURBO)

    assert button.state() == "active"
    assert button.is_armed() is False

    button.set_mode(PerformanceMode.ADAPTIVE)

    assert button.state() == "idle"


def test_analyze_progress_button_keeps_analyze_label_while_running() -> None:
    button = AnalyzeProgressButton("Analyze")

    assert button.height() == GEOMETRY.analyze_button_height

    button.set_progress_percent(42, active=True)

    assert button.display_text() == "Analyze"
    assert button.is_busy() is True
    assert button.shows_spinner() is True
    assert button.is_spinner_active() is True


def test_analyze_progress_button_can_freeze_spinner_while_retaining_progress() -> None:
    button = AnalyzeProgressButton("Analyze")

    button.set_progress_percent(12, active=True, spinner_active=True)
    button.set_spinner_active(False)

    assert button.is_busy() is True
    assert button.shows_spinner() is True
    assert button.is_spinner_active() is False
    assert button.display_text() == "Analyze"


def test_analyze_progress_button_reset_clears_progress_and_spinner() -> None:
    button = AnalyzeProgressButton("Analyze")
    button.set_progress_percent(64, active=True, spinner_active=False)

    button.reset_progress()

    assert button.is_busy() is False
    assert button.shows_spinner() is False
    assert button.is_spinner_active() is False
    assert button.display_text() == "Analyze"
