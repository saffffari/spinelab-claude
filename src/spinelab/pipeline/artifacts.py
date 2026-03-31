from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spinelab.io import CaseStore
from spinelab.models import CaseManifest


def derived_root(store: CaseStore, manifest: CaseManifest) -> Path:
    return store.analytics_derived_dir(manifest.case_id)


def stage_root(store: CaseStore, manifest: CaseManifest, stage: str) -> Path:
    return derived_root(store, manifest) / stage


def stage_file(store: CaseStore, manifest: CaseManifest, stage: str, filename: str) -> Path:
    return stage_root(store, manifest, stage) / filename


def ingest_summary_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "ingest", "asset-summary.json")


def normalized_volume_metadata_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "normalize", "volume-metadata.json")


def segmentation_manifest_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "segmentation", "segmentation.json")


def segmentation_label_map_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "segmentation", "label-map.nii.gz")


def segmentation_run_manifest_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "segmentation", "run-manifest.json")


def performance_trace_path(store: CaseStore, manifest: CaseManifest, stage: str) -> Path:
    return stage_file(store, manifest, stage, "performance-trace.json")


def mesh_manifest_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "mesh", "mesh_manifest.json")


def point_cloud_manifest_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "point-cloud", "point_cloud_manifest.json")


def point_cloud_data_dir(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_root(store, manifest, "point-cloud") / "point-clouds"


def prepared_scene_path(store: CaseStore, manifest: CaseManifest, pose_name: str) -> Path:
    if pose_name == "standing":
        return stage_file(store, manifest, "registration", "prepared_scene_standing.json")
    return stage_file(store, manifest, "point-cloud", "prepared_scene_baseline.json")


def baseline_mesh_dir(store: CaseStore, manifest: CaseManifest) -> Path:
    return store.supine_mesh_dir(manifest.case_id) / "measurement"


def inference_mesh_dir(store: CaseStore, manifest: CaseManifest) -> Path:
    return store.supine_mesh_dir(manifest.case_id) / "inference"


def raw_mesh_dir(store: CaseStore, manifest: CaseManifest) -> Path:
    return store.supine_mesh_dir(manifest.case_id) / "raw"


def point_cloud_dir(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_root(store, manifest, "mesh") / "point-clouds"


def ptv3_summary_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "landmarks", "ptv3_vertebrae.json")


def landmarks_summary_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "landmarks", "landmarks.json")


def pose_graph_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "registration", "pose_graph.json")


def registration_scene_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return store.standing_mesh_dir(manifest.case_id) / "standing_spine.glb"


def measurement_summary_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "measurements", "measurements.json")


def findings_summary_path(store: CaseStore, manifest: CaseManifest) -> Path:
    return stage_file(store, manifest, "findings", "findings-summary.json")


def read_json_artifact(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_artifact(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
