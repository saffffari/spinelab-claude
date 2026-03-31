from pathlib import Path

import nibabel as nib
import numpy as np

from spinelab.models import VolumeMetadata
from spinelab.visualization.viewer_volume import VolumeViewport3D


def test_volume_viewer_loads_nifti_and_switches_modes(qtbot, tmp_path: Path) -> None:
    volume_path = tmp_path / "volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 2.0, 1.0])), str(volume_path))

    volume = VolumeMetadata(
        volume_id="volume-test",
        modality="ct",
        source_path=str(volume_path),
        canonical_path=str(volume_path),
        dimensions=(4, 4, 4),
        voxel_spacing=(1.0, 1.0, 2.0),
        value_range=(0.0, 63.0),
    )

    viewer = VolumeViewport3D("3D", volume)
    qtbot.addWidget(viewer)

    assert viewer._volume_grid is not None  # pyright: ignore[reportPrivateUsage]
    assert viewer.current_render_mode() == "volume"
    assert viewer.current_intensity_preset() == "bone"

    viewer.set_render_mode("isosurface")
    viewer.set_intensity_preset("soft")

    assert viewer.current_render_mode() == "isosurface"
    assert viewer.current_intensity_preset() == "soft"
