from __future__ import annotations

from spinelab.visualization.measurement_overlays import (
    MeasurementOverlayController,
    OverlayGeometry,
    build_measurement_overlay_geometry,
)


def _landmark_payload() -> dict[str, object]:
    return {
        "vertebrae": [
            {
                "vertebra_id": "L1",
                "primitives": {
                    "inferior_endplate_midpoint": {"point_mm": [0.0, 0.0, 0.0]},
                    "inferior_inferior_corner": {"point_mm": [0.0, 0.0, 0.0]},
                    "posterior_wall_line": {
                        "points_mm": [[0.0, 0.0, 0.0], [0.0, -1.0, 0.0]]
                    },
                    "posterior_superior_corner": {"point_mm": [0.0, -1.0, 1.0]},
                    "superior_endplate_midpoint": {"point_mm": [0.0, 0.0, 1.0]},
                    "superior_endplate_plane": {
                        "point_mm": [0.0, 0.0, 1.0],
                        "normal": [0.0, 0.0, 1.0],
                    },
                    "anterior_superior_corner": {"point_mm": [1.0, 1.0, 1.0]},
                    "anterior_inferior_corner": {"point_mm": [1.0, 1.0, 0.0]},
                    "posterior_inferior_corner": {"point_mm": [0.0, -1.0, 0.0]},
                },
            },
            {
                "vertebra_id": "L2",
                "primitives": {
                    "superior_endplate_midpoint": {"point_mm": [0.0, 0.0, -1.0]},
                    "superior_endplate_plane": {
                        "point_mm": [0.0, 0.0, -1.0],
                        "normal": [0.0, 0.0, 1.0],
                    },
                    "anterior_superior_corner": {"point_mm": [1.0, 1.0, -1.0]},
                    "posterior_superior_corner": {"point_mm": [0.0, -1.0, -1.0]},
                    "posterior_wall_line": {
                        "points_mm": [[0.0, 0.0, -1.0], [0.0, -1.0, -1.0]]
                    },
                },
            },
            {
                "vertebra_id": "S1",
                "primitives": {
                    "superior_endplate_midpoint": {"point_mm": [0.0, 0.0, -6.0]},
                    "superior_endplate_plane": {
                        "point_mm": [0.0, 0.0, -6.0],
                        "normal": [0.0, 0.0, 1.0],
                    },
                    "anterior_superior_corner": {"point_mm": [1.5, 1.0, -6.0]},
                    "posterior_superior_corner": {"point_mm": [0.0, -1.0, -6.0]},
                },
            },
            {
                "vertebra_id": "T4",
                "primitives": {
                    "superior_endplate_midpoint": {"point_mm": [0.0, 0.0, 6.0]},
                    "superior_endplate_plane": {
                        "point_mm": [0.0, 0.0, 6.0],
                        "normal": [0.0, 0.0, 1.0],
                    },
                    "anterior_superior_corner": {"point_mm": [1.0, 1.0, 6.0]},
                    "posterior_superior_corner": {"point_mm": [0.0, -1.0, 6.0]},
                },
            },
            {
                "vertebra_id": "T12",
                "primitives": {
                    "inferior_endplate_midpoint": {"point_mm": [0.0, 0.0, 0.5]},
                    "inferior_endplate_plane": {
                        "point_mm": [0.0, 0.0, 0.5],
                        "normal": [0.0, 0.0, 1.0],
                    },
                    "anterior_inferior_corner": {"point_mm": [1.0, 1.0, 0.5]},
                    "posterior_inferior_corner": {"point_mm": [0.0, -1.0, 0.5]},
                },
            },
        ]
    }


def test_disc_height_overlay_uses_selected_segment_primitives() -> None:
    overlay = build_measurement_overlay_geometry("L1-L2 Disc Height", _landmark_payload())

    assert overlay is not None
    assert overlay.label == "L1-L2 Disc Height"
    assert len(overlay.line_segments) == 1
    assert len(overlay.anchor_points) == 2


def test_lumbar_lordosis_overlay_uses_fixed_global_convention() -> None:
    overlay = build_measurement_overlay_geometry("Lumbar Lordosis", _landmark_payload())

    assert overlay is not None
    assert overlay.label == "Lumbar Lordosis"
    assert len(overlay.line_segments) == 3
    assert len(overlay.anchor_points) == 6


def test_overlay_controller_updates_the_viewport_layer() -> None:
    calls: list[tuple[str, OverlayGeometry | None]] = []

    class StubViewport:
        def set_overlay_geometry(self, overlay_id: str, overlay: OverlayGeometry | None) -> None:
            calls.append((overlay_id, overlay))

    controller = MeasurementOverlayController(
        StubViewport(),
        lambda: _landmark_payload(),
    )

    overlay = controller.refresh("L1-L2 Listhesis")

    assert overlay is not None
    assert calls[-1][0] == "automatic-measurement"
    assert calls[-1][1] is overlay
