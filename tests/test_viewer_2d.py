from pathlib import Path

import nibabel as nib
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, qRgb
from PySide6.QtWidgets import QWidget

from spinelab.models import StudyAsset
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, qcolor_from_css
from spinelab.visualization.viewer_2d import (
    EMPTY_STATE_ICON_PATH,
    ImageViewport2D,
    SliceCanvas,
    XrayProjection,
    ZStackViewport2D,
    empty_placeholder_icon_rect,
    load_ct_stack_images,
    render_empty_placeholder,
    render_loaded_ct_slice,
    stack_preview_slice_index,
    wheel_uses_slice_navigation,
)
from spinelab.visualization.viewport_gnomon import (
    ViewportGnomonOverlay,
    position_gnomon_overlay,
)


def test_load_ct_stack_images_reads_full_directory_into_memory(tmp_path: Path) -> None:
    for index, color in enumerate((24, 96, 168), start=1):
        image = QImage(12, 12, QImage.Format.Format_ARGB32)
        image.fill(qRgb(color, color, color))
        image.save(str(tmp_path / f"slice-{index}.png"))

    slice_paths, loaded_slices = load_ct_stack_images(tmp_path)

    assert [path.name for path in slice_paths] == [
        "slice-1.png",
        "slice-2.png",
        "slice-3.png",
    ]
    assert len(loaded_slices) == 3
    assert all(not image.isNull() for image in loaded_slices)


def test_zstack_viewport_uses_slider_for_loaded_stack(qtbot, tmp_path: Path) -> None:
    for index, color in enumerate((40, 120, 200), start=1):
        image = QImage(16, 16, QImage.Format.Format_ARGB32)
        image.fill(qRgb(color, color, color))
        image.save(str(tmp_path / f"ct-{index}.png"))

    asset = StudyAsset(
        asset_id="ct-stack",
        kind="ct_zstack",
        label="CT",
        source_path=str(tmp_path),
        managed_path=str(tmp_path),
    )

    widget = ZStackViewport2D("CT Stack")
    qtbot.addWidget(widget)

    widget.set_asset(asset)

    assert widget._slice_slider.maximum() == 3
    assert widget._slice_slider.isEnabled() is True
    assert widget.canvas.slice_count == 3
    assert widget.canvas.slice_index == stack_preview_slice_index(3)

    widget._slice_slider.setValue(2)

    assert widget.canvas.slice_index == 1
    assert widget.title_label.isHidden() is False
    assert widget.title_label.text() == "CT Stack"
    assert widget.status_label.text().endswith("2/3")


def test_wheel_behavior_uses_slice_navigation_only_for_ct_without_control() -> None:
    assert wheel_uses_slice_navigation("ct", Qt.KeyboardModifier.NoModifier) is True
    assert wheel_uses_slice_navigation("ct", Qt.KeyboardModifier.ControlModifier) is False
    assert wheel_uses_slice_navigation("xray", Qt.KeyboardModifier.NoModifier) is False


def test_stack_preview_slice_index_uses_mid_stack_rounding() -> None:
    assert stack_preview_slice_index(1) == 0
    assert stack_preview_slice_index(2) == 0
    assert stack_preview_slice_index(3) == 1
    assert stack_preview_slice_index(4) == 1
    assert stack_preview_slice_index(5) == 2


def test_image_viewport_shows_title_and_live_status(qtbot, tmp_path: Path) -> None:
    image = QImage(16, 16, QImage.Format.Format_ARGB32)
    image.fill(qRgb(180, 180, 180))
    image_path = tmp_path / "ap-view.png"
    image.save(str(image_path))

    asset = StudyAsset(
        asset_id="xray-ap",
        kind="xray_2d",
        label="X-Ray",
        source_path=str(image_path),
        managed_path=str(image_path),
    )

    widget = ImageViewport2D("X-Ray AP", XrayProjection.AP)
    qtbot.addWidget(widget)

    assert widget.title_label.isHidden() is False
    assert widget.title_label.text() == "X-Ray AP"
    assert widget.status_label.text() == "Unassigned"

    widget.set_asset(asset)

    assert widget.title_label.text() == "X-Ray AP"
    assert widget.status_label.text() == "ap-view.png"


def test_slice_canvas_uses_full_image_block_for_fit_geometry(qtbot) -> None:
    canvas = SliceCanvas("xray", "AP", "")
    qtbot.addWidget(canvas)
    canvas.resize(320, 240)

    content_rect = canvas._content_rect()

    assert content_rect.x() == 0.0
    assert content_rect.y() == 0.0
    assert content_rect.width() == 320.0
    assert content_rect.height() == 240.0


def test_empty_placeholder_uses_document_add_icon_asset() -> None:
    image = render_empty_placeholder(220, 180, "X-Ray AP", "")
    background_pixel = image.pixelColor(0, 0)
    has_non_background_pixels = False
    for y in range(40, 120, 8):
        for x in range(60, 160, 8):
            if image.pixelColor(x, y) != background_pixel:
                has_non_background_pixels = True
                break
        if has_non_background_pixels:
            break

    assert EMPTY_STATE_ICON_PATH.exists()
    assert background_pixel == qcolor_from_css(THEME_COLORS.viewport_empty_bg)
    assert has_non_background_pixels is True


def test_empty_placeholder_icon_rect_stays_centered_in_block() -> None:
    rect = empty_placeholder_icon_rect(220, 180)

    assert rect.x() == (220 - rect.width()) // 2
    assert rect.y() == (180 - rect.height()) // 2


def test_render_loaded_ct_slice_uses_real_nifti_mid_slice(tmp_path: Path) -> None:
    volume = np.zeros((8, 8, 5), dtype=np.float32)
    volume[2:6, 2:6, 2] = 255.0
    source_path = tmp_path / "preview-volume.nii.gz"
    nib.save(nib.Nifti1Image(volume, np.eye(4)), str(source_path))

    image = render_loaded_ct_slice(160, 160, source_path, 2, 5)
    center = image.pixelColor(image.width() // 2, image.height() // 2)

    assert center.red() > 200
    assert center.green() > 200
    assert center.blue() > 200


def test_image_viewport_freezes_to_snapshot_during_layout_transition(qtbot) -> None:
    widget = ImageViewport2D("X-Ray AP", XrayProjection.AP)
    qtbot.addWidget(widget)
    widget.resize(320, 240)

    widget.set_layout_transition_active(True)

    assert widget._transition_overlay is not None
    assert widget._surface is not None
    assert widget._transition_overlay.parentWidget() is widget._surface
    assert widget._surface.isHidden() is False
    assert widget.canvas.isHidden() is True

    widget.set_layout_transition_active(False)

    assert widget._transition_overlay is None
    assert widget._surface.isHidden() is False
    assert widget.canvas.isHidden() is False


def test_position_gnomon_overlay_anchors_widget_to_surface_bottom_left(qtbot) -> None:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(320, 240)
    surface = QWidget(host)
    surface.setGeometry(24, 18, 200, 160)
    gnomon = ViewportGnomonOverlay(host)

    position_gnomon_overlay(gnomon, surface)

    assert gnomon.x() == surface.x() + GEOMETRY.overlay_padding
    assert (
        gnomon.y()
        == surface.y()
        + surface.height()
        - gnomon.height()
        - GEOMETRY.overlay_padding
    )


def test_import_viewports_use_shared_gnomon_overlay(qtbot) -> None:
    xray_viewport = ImageViewport2D("X-Ray AP", XrayProjection.AP)
    lat_viewport = ImageViewport2D("X-Ray Lat", XrayProjection.LAT)
    ct_viewport = ZStackViewport2D("CT Stack")
    qtbot.addWidget(xray_viewport)
    qtbot.addWidget(lat_viewport)
    qtbot.addWidget(ct_viewport)

    xray_gnomons = xray_viewport.findChildren(ViewportGnomonOverlay)
    lat_gnomons = lat_viewport.findChildren(ViewportGnomonOverlay)
    ct_gnomons = ct_viewport.findChildren(ViewportGnomonOverlay)

    assert len(xray_gnomons) == 1
    assert len(lat_gnomons) == 1
    assert len(ct_gnomons) == 1
    assert xray_gnomons[0].parentWidget() is xray_viewport
    assert lat_gnomons[0].parentWidget() is lat_viewport
    assert ct_gnomons[0].parentWidget() is ct_viewport
    assert xray_gnomons[0].spec.horizontal_negative == "R"
    assert xray_gnomons[0].spec.horizontal_positive == "L"
    assert xray_gnomons[0].spec.vertical_negative == "I"
    assert xray_gnomons[0].spec.vertical_positive == "S"
    assert lat_gnomons[0].spec.horizontal_negative == "P"
    assert lat_gnomons[0].spec.horizontal_positive == "A"
    assert lat_gnomons[0].spec.vertical_negative == "I"
    assert lat_gnomons[0].spec.vertical_positive == "S"
    assert ct_gnomons[0].spec.horizontal_negative == "R"
    assert ct_gnomons[0].spec.horizontal_positive == "L"
    assert ct_gnomons[0].spec.vertical_negative == "P"
    assert ct_gnomons[0].spec.vertical_positive == "A"
