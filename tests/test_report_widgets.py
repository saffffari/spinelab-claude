from spinelab.workspaces.report_widgets import (
    RadialSummaryWidget,
    RegionalBarChartWidget,
    TrendChartWidget,
)


def test_trend_chart_exposes_axis_labels_with_units(qtbot) -> None:
    widget = TrendChartWidget()
    qtbot.addWidget(widget)

    x_label, y_label = widget.axis_labels()

    assert x_label == "Vertebral Level (ID)"
    assert y_label == "Relative Motion (mm)"


def test_regional_bar_chart_exposes_axis_labels_with_units(qtbot) -> None:
    widget = RegionalBarChartWidget()
    qtbot.addWidget(widget)

    x_label, y_label = widget.axis_labels()

    assert x_label == "Motion Magnitude (mm)"
    assert y_label == "Spinal Region (region)"


def test_radial_summary_exposes_axis_labels_with_units(qtbot) -> None:
    widget = RadialSummaryWidget()
    qtbot.addWidget(widget)

    x_label, y_label = widget.axis_labels()

    assert x_label == "Regional Distribution (region)"
    assert y_label == "Motion Magnitude (mm)"
