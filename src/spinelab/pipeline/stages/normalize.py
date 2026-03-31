from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import pydicom
from PySide6.QtGui import QImageReader

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineArtifact, VolumeMetadata
from spinelab.models.manifest import make_id
from spinelab.pipeline.artifacts import normalized_volume_metadata_path, write_json_artifact
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.visualization.viewer_2d import resolve_slice_sources

_NIFTI_SUFFIXES = {".nii", ".nii.gz"}


def _canonical_modality(asset_kind: str, asset_label: str) -> str:
    lowered_label = asset_label.lower()
    if "mri" in lowered_label or asset_kind == "mri_2d":
        return "mri"
    return "ct"


def _nifti_suffix(path: Path) -> str:
    return "".join(path.suffixes).lower()


def _orientation_from_nifti(image: Any) -> str:
    try:
        axis_codes = nib.orientations.aff2axcodes(image.affine)
    except Exception:
        return ""
    return "".join(str(code) for code in axis_codes if code is not None)


def _build_volume_from_nifti(
    asset_id: str,
    source_path: Path,
    modality: str,
) -> VolumeMetadata | None:
    image_any: Any = nib.load(str(source_path))
    data = np.asarray(image_any.dataobj)
    if data.ndim == 2:
        dimensions = (int(data.shape[0]), int(data.shape[1]), 1)
    else:
        dimensions = (int(data.shape[0]), int(data.shape[1]), int(data.shape[2]))
    header = image_any.header
    zooms = tuple(float(value) for value in header.get_zooms()[:3])
    if len(zooms) < 3:
        zooms = zooms + (1.0,) * (3 - len(zooms))
    value_range = (float(np.min(data)), float(np.max(data)))
    return VolumeMetadata(
        volume_id=make_id("volume"),
        modality=modality,
        source_path=str(source_path),
        canonical_path=str(source_path),
        dimensions=dimensions,
        asset_id=asset_id,
        voxel_spacing=(zooms[0], zooms[1], zooms[2]),
        orientation=_orientation_from_nifti(image_any),
        value_range=value_range,
        source_coordinate_frame="native-image",
        coordinate_frame="normalized-volume",
        native_to_canonical_transform={
            "type": "identity-resample",
            "note": "Current normalize stage keeps canonical path aligned to source volume.",
        },
        qc_summary="Volume readable for GUI-backed review.",
        provenance="analyze.normalize",
    )


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    reader = QImageReader(str(path))
    size = reader.size()
    if size.isValid():
        return size.width(), size.height()
    if path.suffix.lower() == ".dcm":
        try:
            dataset = pydicom.dcmread(str(path), stop_before_pixels=True)
        except Exception:
            return None
        rows = int(getattr(dataset, "Rows", 0) or 0)
        columns = int(getattr(dataset, "Columns", 0) or 0)
        if rows > 0 and columns > 0:
            return columns, rows
    return None


def _build_volume_from_stack(
    asset_id: str,
    source_path: Path,
    modality: str,
) -> VolumeMetadata | None:
    slice_paths = resolve_slice_sources(source_path)
    if not slice_paths:
        return None
    dimensions_2d = _image_dimensions(slice_paths[0])
    if dimensions_2d is None:
        return None
    spacing = (1.0, 1.0, 1.0)
    if slice_paths[0].suffix.lower() == ".dcm":
        try:
            dataset = pydicom.dcmread(str(slice_paths[0]), stop_before_pixels=True)
        except Exception:
            dataset = None
        if dataset is not None:
            pixel_spacing = getattr(dataset, "PixelSpacing", None)
            slice_spacing = getattr(dataset, "SliceThickness", None)
            if pixel_spacing is not None and len(pixel_spacing) >= 2:
                spacing = (
                    float(pixel_spacing[1]),
                    float(pixel_spacing[0]),
                    float(slice_spacing or 1.0),
                )
    return VolumeMetadata(
        volume_id=make_id("volume"),
        modality=modality,
        source_path=str(source_path),
        canonical_path=str(source_path),
        dimensions=(dimensions_2d[0], dimensions_2d[1], len(slice_paths)),
        asset_id=asset_id,
        voxel_spacing=spacing,
        orientation="slice-stack",
        value_range=(0.0, 255.0),
        source_coordinate_frame="native-image",
        coordinate_frame="normalized-volume",
        native_to_canonical_transform={
            "type": "stack-pass-through",
            "note": "Current normalize stage preserves imported stack ordering for review.",
        },
        qc_summary="Slice stack available for GUI-backed review.",
        provenance="analyze.normalize",
    )


def run_normalize_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    volumes: list[VolumeMetadata] = []
    warnings: list[str] = []
    for asset in manifest.assets:
        if asset.kind not in {"ct_zstack", "mri_2d"}:
            continue
        source_path = Path(asset.managed_path)
        modality = _canonical_modality(asset.kind, asset.label)
        volume: VolumeMetadata | None = None
        suffix = _nifti_suffix(source_path)
        if source_path.is_file() and suffix in _NIFTI_SUFFIXES:
            try:
                volume = _build_volume_from_nifti(asset.asset_id, source_path, modality)
            except Exception as exc:
                warnings.append(f"Unable to normalize {source_path.name}: {exc}")
        elif source_path.is_dir() or asset.kind == "ct_zstack":
            volume = _build_volume_from_stack(asset.asset_id, source_path, modality)
        if volume is not None:
            volumes.append(volume)

    summary_path = normalized_volume_metadata_path(store, manifest)
    payload = {
        "case_id": manifest.case_id,
        "volume_count": len(volumes),
        "volumes": [asdict(volume) for volume in volumes],
        "warnings": warnings,
        "gui_primary_surface": "import",
    }
    write_json_artifact(summary_path, payload)
    artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="Normalized Volume Metadata",
        path=str(summary_path),
        stage=PipelineStageName.NORMALIZE.value,
        artifact_type="normalized-volume",
        coordinate_frame="normalized-volume",
        review_surface="import",
        summary=f"{len(volumes)} canonical review volume(s) prepared for downstream stages.",
        metadata={"volume_count": str(len(volumes))},
    )
    return StageExecutionResult(
        stage=PipelineStageName.NORMALIZE,
        message=f"Normalized {len(volumes)} review volume(s).",
        outputs=[str(summary_path)],
        artifacts=[artifact],
        volumes=volumes,
        warnings=warnings,
    )
