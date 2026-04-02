from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from spinelab.io import CaseStore
from spinelab.models import CaseManifest, SegmentationProfile
from spinelab.pipeline.manifest_bridge import apply_stage_result
from spinelab.pipeline.stages.mesh import run_mesh_stage
from spinelab.pipeline.stages.normalize import run_normalize_stage
from spinelab.pipeline.stages.segmentation import run_segmentation_stage
from spinelab.pipeline.stages.mesh_pipeline import (
    DEFAULT_EXTRACTION_ALGORITHM,
    SURFACE_NETS_ALGORITHM,
    MeshPipelineConfig,
    VertebraSegmentationEntry,
    binary_surface_distance_metrics,
    dice_score,
    extract_vertebra_mesh,
    rasterize_polydata,
)


def test_mesh_stage_persists_production_mesh_contracts(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Mesh Stage Case"
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "mesh_case_volume.nii.gz"
    volume_data = np.arange(27, dtype=np.int16).reshape((3, 3, 3))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.5, 1.5, 2.0, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    for stage_runner in (run_normalize_stage, run_segmentation_stage, run_mesh_stage):
        result = stage_runner(store, manifest)
        apply_stage_result(manifest, result)
        store.save_manifest(manifest)

    mesh_artifact = next(
        artifact
        for artifact in manifest.artifacts
        if artifact.artifact_type == "mesh-manifest"
    )
    payload = json.loads(Path(mesh_artifact.path).read_text(encoding="utf-8"))

    assert payload["pipeline_version"] == "mesh-pipeline.v1"
    assert payload["canonical_mesh_type"] == "triangles"
    assert payload["extraction_algorithm"] == DEFAULT_EXTRACTION_ALGORITHM
    assert payload["source_coordinate_frame"] == "normalized-volume"
    assert payload["qc_summary"]["produced_vertebra_count"] > 0
    assert SURFACE_NETS_ALGORITHM in payload["benchmark_candidates"]

    first_complete = next(entry for entry in payload["vertebrae"] if entry["status"] == "complete")
    raw_path = Path(first_complete["raw_mesh_path"])
    baseline_path = Path(first_complete["high_resolution_mesh_path"])
    inference_path = Path(first_complete["inference_mesh_path"])
    point_cloud_path = Path(first_complete["point_cloud_path"])

    assert raw_path.exists()
    assert baseline_path.exists()
    assert inference_path.exists()
    assert point_cloud_path.exists()
    assert baseline_path.read_bytes().startswith(b"ply\nformat binary_little_endian 1.0\n")

    point_cloud = np.load(point_cloud_path)
    assert point_cloud["points"].shape == (MeshPipelineConfig().point_cloud_size, 3)
    assert point_cloud["normals"].shape == (MeshPipelineConfig().point_cloud_size, 3)

    pyvista = pytest.importorskip("pyvista")
    baseline_mesh = pyvista.read(baseline_path)
    assert baseline_mesh.n_cells > 0
    assert np.all(baseline_mesh.faces.reshape(-1, 4)[:, 0] == 3)


def test_mesh_pipeline_sampling_and_benchmark_metrics_are_deterministic() -> None:
    label_map = np.zeros((16, 16, 16), dtype=np.int16)
    label_map[4:11, 4:12, 5:10] = 1
    affine = np.diag([1.0, 1.0, 1.2, 1.0])
    entry = VertebraSegmentationEntry("L1", 1)

    first = extract_vertebra_mesh(
        label_map,
        affine,
        entry,
        config=MeshPipelineConfig(point_cloud_size=2048),
        point_cloud_seed_key="mesh-determinism",
    )
    second = extract_vertebra_mesh(
        label_map,
        affine,
        entry,
        config=MeshPipelineConfig(point_cloud_size=2048),
        point_cloud_seed_key="mesh-determinism",
    )

    assert first.status == "complete"
    assert second.status == "complete"
    assert np.allclose(first.point_cloud, second.point_cloud)
    assert np.allclose(first.point_normals, second.point_normals)

    revoxelized = rasterize_polydata(
        first.measurement_mesh,
        shape=first.roi_mask.shape,
        affine=first.roi_affine,
    )
    assert dice_score(first.roi_mask, revoxelized) > 0.8

    surface_metrics = binary_surface_distance_metrics(
        first.roi_mask,
        revoxelized,
        spacing=(1.0, 1.0, 1.2),
    )
    assert surface_metrics["assd_mm"] is not None
    assert surface_metrics["hd95_mm"] is not None
