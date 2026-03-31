"""Workspace implementations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .import_workspace import ImportWorkspace
    from .measurement_workspace import MeasurementWorkspace
    from .report_workspace import ReportWorkspace

__all__ = ["ImportWorkspace", "MeasurementWorkspace", "ReportWorkspace"]


def __getattr__(name: str):
    if name == "ImportWorkspace":
        from .import_workspace import ImportWorkspace

        return ImportWorkspace
    if name == "MeasurementWorkspace":
        from .measurement_workspace import MeasurementWorkspace

        return MeasurementWorkspace
    if name == "ReportWorkspace":
        from .report_workspace import ReportWorkspace

        return ReportWorkspace
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
