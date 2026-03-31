from pathlib import Path

import nibabel as nib
import numpy as np

from spinelab.exports.testing_drr import generate_testing_drrs
from spinelab.io.case_store import CaseStore
from spinelab.models import CaseManifest


def test_generate_testing_drrs_writes_case_drr_images_and_assigns_roles(tmp_path: Path) -> None:
    store = CaseStore(tmp_path)
    manifest = CaseManifest.demo()
    store.save_manifest(manifest)

    ct_volume_path = tmp_path / "source-volume.nii.gz"
    volume = np.linspace(-200.0, 1200.0, num=32 * 24 * 16, dtype=np.float32).reshape(32, 24, 16)
    nib.save(nib.Nifti1Image(volume, affine=np.eye(4)), str(ct_volume_path))

    ct_asset = store.import_asset(manifest, ct_volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(ct_asset.asset_id, "ct_stack")
    store.save_manifest(manifest)

    result = generate_testing_drrs(store, manifest)

    assert result.generation_mode == "testing_volume_projection"
    assert result.ap_path == store.drr_dir(manifest.case_id) / "testing_drr_ap.png"
    assert result.lat_path == store.drr_dir(manifest.case_id) / "testing_drr_lat.png"
    assert result.ap_path.exists() is True
    assert result.lat_path.exists() is True

    reloaded = store.load_manifest(manifest.case_id)
    ap_asset = reloaded.get_asset_for_role("xray_ap")
    lat_asset = reloaded.get_asset_for_role("xray_lat")
    assert ap_asset is not None
    assert lat_asset is not None
    assert Path(ap_asset.managed_path) == result.ap_path
    assert Path(lat_asset.managed_path) == result.lat_path
    assert any(run.stage == "drr" and run.status == "complete" for run in reloaded.pipeline_runs)
