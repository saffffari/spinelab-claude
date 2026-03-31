from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import nibabel as nib
import numpy as np
from PySide6.QtGui import QImage

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineRun, StudyAsset
from spinelab.models.manifest import make_id


@dataclass(frozen=True, slots=True)
class TestingDrrResult:
    ap_path: Path
    lat_path: Path
    generation_mode: str


def generate_testing_drrs(
    store: CaseStore,
    manifest: CaseManifest,
) -> TestingDrrResult:
    if not store.case_is_editable(manifest.case_id):
        raise ValueError("Testing DRRs can only be generated for managed cases.")

    ct_path = _primary_ct_volume_path(store, manifest)
    if ct_path is None:
        raise ValueError("No CT volume is assigned to this case.")
    if not ct_path.exists() or not ct_path.is_file():
        raise ValueError("The assigned CT volume is missing from disk.")

    volume = _load_volume(ct_path)
    ap_projection = _project_volume_for_testing(volume, axis=1)
    lat_projection = _project_volume_for_testing(volume, axis=0)

    output_dir = store.drr_dir(manifest.case_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    ap_path = output_dir / "testing_drr_ap.png"
    lat_path = output_dir / "testing_drr_lat.png"
    _qimage_from_array(ap_projection).save(str(ap_path))
    _qimage_from_array(lat_projection).save(str(lat_path))

    _upsert_testing_drr_asset(
        manifest,
        ap_path,
        role="xray_ap",
        label="Testing DRR AP",
    )
    _upsert_testing_drr_asset(
        manifest,
        lat_path,
        role="xray_lat",
        label="Testing DRR LAT",
    )
    manifest.pipeline_runs.append(
        PipelineRun(
            stage="drr",
            status="complete",
            backend_tool="spinelab-testing",
            environment_id="app",
            device="cpu",
            outputs=["xray_ap", "xray_lat"],
            message=(
                "Generated temporary bilateral AP/LAT testing DRRs from the case CT volume. "
                "These are projection surrogates, not calibrated NanoDRR outputs."
            ),
        )
    )
    store.save_manifest(manifest)
    return TestingDrrResult(
        ap_path=ap_path,
        lat_path=lat_path,
        generation_mode="testing_volume_projection",
    )


def _primary_ct_volume_path(store: CaseStore, manifest: CaseManifest) -> Path | None:
    ct_asset = manifest.get_asset_for_role("ct_stack")
    if ct_asset is not None:
        ct_path = Path(ct_asset.managed_path)
        if ct_path.is_file():
            return ct_path
    for asset in manifest.assets:
        if asset.kind != "ct_zstack":
            continue
        ct_path = Path(asset.managed_path)
        if ct_path.is_file():
            return ct_path
    ct_dir = store.ct_dir(manifest.case_id)
    if ct_dir.exists():
        for candidate in sorted(ct_dir.iterdir(), key=lambda path: path.name.lower()):
            if candidate.is_file() and _looks_like_volume(candidate):
                return candidate
    return None


def _load_volume(source_path: Path) -> np.ndarray:
    try:
        volume_image = cast(Any, nib.load(str(source_path)))
    except Exception as exc:
        raise ValueError(f"Unable to read CT volume: {exc}") from exc
    volume = np.asarray(volume_image.dataobj, dtype=np.float32)
    if volume.ndim == 4:
        volume = volume[..., 0]
    if volume.ndim != 3:
        raise ValueError("CT volume must be three-dimensional.")
    return volume


def _project_volume_for_testing(volume: np.ndarray, *, axis: int) -> np.ndarray:
    clipped = np.clip(volume, -200.0, 1600.0)
    attenuation = (clipped + 200.0) / 1800.0
    attenuation = np.clip(attenuation, 0.0, 1.0)
    projection = np.log1p(np.sum(attenuation, axis=axis))
    return np.rot90(projection)


def _qimage_from_array(array: np.ndarray) -> QImage:
    pixel_data = np.nan_to_num(np.asarray(array, dtype=np.float32), nan=0.0)
    if pixel_data.ndim == 3:
        pixel_data = pixel_data[:, :, 0]
    if pixel_data.size == 0:
        normalized = np.zeros((1, 1), dtype=np.uint8)
    else:
        min_value = float(np.min(pixel_data))
        max_value = float(np.max(pixel_data))
        if max_value <= min_value:
            normalized = np.zeros(pixel_data.shape, dtype=np.uint8)
        else:
            normalized = np.clip(
                ((pixel_data - min_value) / (max_value - min_value)) * 255.0,
                0.0,
                255.0,
            ).astype(np.uint8)
    contiguous = np.ascontiguousarray(normalized)
    height, width = contiguous.shape
    image = QImage(
        contiguous.data,
        width,
        height,
        contiguous.strides[0],
        QImage.Format.Format_Grayscale8,
    )
    return image.copy()


def _upsert_testing_drr_asset(
    manifest: CaseManifest,
    output_path: Path,
    *,
    role: str,
    label: str,
) -> None:
    asset = _find_existing_testing_drr_asset(manifest, role)
    if asset is None:
        asset = StudyAsset(
            asset_id=make_id("asset"),
            kind="xray_2d",
            label=label,
            source_path=str(output_path),
            managed_path=str(output_path),
        )
        manifest.assets.append(asset)
    asset.kind = "xray_2d"
    asset.label = label
    asset.source_path = str(output_path)
    asset.managed_path = str(output_path)
    asset.status = "ready"
    manifest.assign_asset_to_role(asset.asset_id, role)


def _find_existing_testing_drr_asset(manifest: CaseManifest, role: str) -> StudyAsset | None:
    assigned_asset = manifest.get_asset_for_role(role)
    if (
        assigned_asset is not None
        and Path(assigned_asset.managed_path).name.startswith("testing_drr_")
    ):
        return assigned_asset
    for asset in manifest.assets:
        if Path(asset.managed_path).name == _testing_drr_file_name(role):
            return asset
    return None


def _testing_drr_file_name(role: str) -> str:
    if role == "xray_lat":
        return "testing_drr_lat.png"
    return "testing_drr_ap.png"


def _looks_like_volume(path: Path) -> bool:
    suffix = "".join(path.suffixes).lower()
    return suffix in {".nii", ".nii.gz", ".nrrd", ".mha", ".mhd"}
