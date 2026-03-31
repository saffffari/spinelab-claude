from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import numpy as np
from PySide6.QtCore import QSettings

import spinelab.pipeline.stages.segmentation as segmentation_module
import spinelab.segmentation.bundles as bundles_module
from spinelab.io import CaseStore
from spinelab.models import CaseManifest, PipelineRun
from spinelab.pipeline.device import RuntimeDeviceSelection
from spinelab.pipeline.manifest_bridge import apply_stage_result
from spinelab.pipeline.stages.common import SEGMENTATION_MODEL_NAME
from spinelab.pipeline.stages.mesh import run_mesh_stage
from spinelab.pipeline.stages.normalize import run_normalize_stage
from spinelab.pipeline.stages.segmentation import run_segmentation_stage
from spinelab.segmentation import (
    DEBUG_SEGMENTATION_BUNDLES_ENV_VAR,
    PredictionBatchResult,
    PredictionOutput,
    SegmentationBundleRegistry,
    install_nnunet_bundle,
    install_skellytour_bundle,
    install_totalsegmentator_bundle,
)
from spinelab.segmentation_profiles import SegmentationProfile, canonical_segmentation_profile
from spinelab.services import SettingsService


def _prepare_ct_case(
    tmp_path: Path,
    *,
    segmentation_profile: str,
) -> tuple[CaseStore, CaseManifest]:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Segmentation Test"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = segmentation_profile

    volume_path = tmp_path / "ct_volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.2, 1.2, 2.5, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")
    store.save_manifest(manifest)

    normalize_result = run_normalize_stage(store, manifest)
    apply_stage_result(manifest, normalize_result)
    store.save_manifest(manifest)
    return store, manifest


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "segmentation-stage.ini"),
        QSettings.Format.IniFormat,
    )
    return service


def _write_fake_trainer_root(tmp_path: Path) -> Path:
    trainer_root = (
        tmp_path
        / "legacy-results"
        / "Dataset321_VERSE20Vertebrae"
        / "nnUNetTrainer__nnUNetResEncL_24G__3d_fullres"
    )
    (trainer_root / "fold_0").mkdir(parents=True, exist_ok=True)
    (trainer_root / "fold_1").mkdir(parents=True, exist_ok=True)
    (trainer_root / "plans.json").write_text("{}", encoding="utf-8")
    (trainer_root / "dataset.json").write_text("{}", encoding="utf-8")
    (trainer_root / "fold_0" / "checkpoint_final.pth").write_bytes(b"checkpoint")
    (trainer_root / "fold_0" / "checkpoint_best.pth").write_bytes(b"checkpoint")
    (trainer_root / "fold_1" / "checkpoint_latest.pth").write_bytes(b"checkpoint")
    return trainer_root


def _enable_debug_segmentation_bundles(monkeypatch) -> None:
    monkeypatch.setenv(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR, "1")


def test_segmentation_stage_emits_scaffold_payload(tmp_path: Path) -> None:
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.SCAFFOLD.value,
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)

    segmentation_artifact = next(
        artifact for artifact in manifest.artifacts if artifact.artifact_type == "segmentation"
    )
    payload = json.loads(Path(segmentation_artifact.path).read_text(encoding="utf-8"))
    label_map = np.asarray(nib.load(payload["label_map_path"]).dataobj)

    assert payload["segmentation_profile"] == SegmentationProfile.SCAFFOLD.value
    assert payload["model_name"] == SEGMENTATION_MODEL_NAME
    assert payload["checkpoint_id"] == "pending-verse20-training"
    assert payload["qc_summary"]["status"] == "scaffold"
    assert payload["level_map"]["C7"] == 1
    assert payload["level_map"]["S1"] == len(payload["vertebrae"])
    assert set(np.unique(label_map).tolist()) >= {0, 1}


def test_segmentation_profiles_accept_only_current_values(tmp_path: Path) -> None:
    assert canonical_segmentation_profile(SegmentationProfile.SCAFFOLD.value) == (
        SegmentationProfile.SCAFFOLD.value
    )
    assert canonical_segmentation_profile("legacy-bootstrap") == (
        SegmentationProfile.PRODUCTION.value
    )

    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.SCAFFOLD.value,
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)

    segmentation_artifact = next(
        artifact for artifact in manifest.artifacts if artifact.artifact_type == "segmentation"
    )
    payload = json.loads(Path(segmentation_artifact.path).read_text(encoding="utf-8"))

    assert manifest.segmentation_profile == SegmentationProfile.SCAFFOLD.value
    assert payload["segmentation_profile"] == SegmentationProfile.SCAFFOLD.value


def test_production_segmentation_stage_emits_bundle_backed_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _enable_debug_segmentation_bundles(monkeypatch)
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        settings=settings,
        activate=True,
        active_checkpoint_id="fold-0:checkpoint_final",
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    class FakeDriver:
        driver_id = "nnunetv2"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            for index, label_value in enumerate(runtime_model.label_mapping.values()):
                coordinates = np.unravel_index(index, label_map.shape)
                label_map[coordinates] = label_value
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("python", "nnunet_predict_sidecar.py"),
                log_path=working_dir / "sidecar.log",
                device=device,
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)
    mesh_result = run_mesh_stage(store, manifest)
    apply_stage_result(manifest, mesh_result)

    segmentation_artifact = next(
        artifact for artifact in manifest.artifacts if artifact.artifact_type == "segmentation"
    )
    payload = json.loads(Path(segmentation_artifact.path).read_text(encoding="utf-8"))
    run_manifest_path = Path(payload["segmentation_run_manifest_path"])
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))

    assert payload["segmentation_profile"] == SegmentationProfile.PRODUCTION.value
    assert payload["model_bundle_id"] == bundle.bundle_id
    assert payload["model_family"] == bundle.family
    assert payload["driver_id"] == "nnunetv2"
    assert payload["runtime_environment_id"] == bundle.environment_id
    assert payload["resolved_checkpoint_id"] == bundle.active_checkpoint_id
    assert payload["qc_summary"]["vertebra_count"] == len(payload["vertebrae"])
    assert run_manifest["model_bundle_id"] == bundle.bundle_id
    assert run_manifest["resolved_checkpoint_id"] == bundle.active_checkpoint_id
    assert {
        "segmentation",
        "segmentation-label-map",
        "segmentation-run-manifest",
    }.issubset({artifact.artifact_type for artifact in result.artifacts})
    assert any(artifact.artifact_type == "mesh-manifest" for artifact in mesh_result.artifacts)


def test_production_segmentation_stage_fails_closed_without_active_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    try:
        run_segmentation_stage(store, manifest)
    except RuntimeError as exc:
        assert "No active production segmentation bundle is configured" in str(exc)
    else:
        raise AssertionError("Expected production segmentation to fail without an active bundle.")


def test_production_segmentation_stage_allows_cpu_fallback_without_cuda_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _enable_debug_segmentation_bundles(monkeypatch)
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    registry = SegmentationBundleRegistry(store, settings=settings)
    install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        settings=settings,
        activate=True,
        active_checkpoint_id="fold-0:checkpoint_final",
    )

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cpu",
            backend="cpu",
            cuda_version=None,
            gpu_name=None,
            total_vram_mb=None,
            backend_health={"status": "cpu-only"},
        ),
    )
    observed_devices: list[str] = []

    class FakeDriver:
        driver_id = "nnunetv2"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta
            observed_devices.append(device)
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            label_map[(0, 0, 0)] = runtime_model.label_mapping["C7"]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("python", "nnunet_predict_sidecar.py"),
                log_path=working_dir / "sidecar.log",
                device=device,
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)

    assert observed_devices == ["cpu"]


def test_production_segmentation_stage_only_reports_detected_vertebrae(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _enable_debug_segmentation_bundles(monkeypatch)
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        settings=settings,
        activate=True,
        active_checkpoint_id="fold-0:checkpoint_final",
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    class FakeSparseDriver:
        driver_id = "nnunetv2"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta, device
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            present_levels = ("C7", "T1", "T2")
            for index, level_id in enumerate(present_levels):
                coordinates = np.unravel_index(index, label_map.shape)
                label_map[coordinates] = runtime_model.label_mapping[level_id]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("python", "nnunet_predict_sidecar.py"),
                log_path=working_dir / "sidecar.log",
                device="cuda",
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeSparseDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)
    segmentation_artifact = next(
        artifact for artifact in manifest.artifacts if artifact.artifact_type == "segmentation"
    )
    payload = json.loads(Path(segmentation_artifact.path).read_text(encoding="utf-8"))

    assert payload["model_bundle_id"] == bundle.bundle_id
    assert payload["qc_summary"]["vertebra_count"] == 3
    assert (
        payload["qc_summary"]["expected_vertebra_count"]
        > payload["qc_summary"]["vertebra_count"]
    )
    assert [entry["vertebra_id"] for entry in payload["vertebrae"]] == ["C7", "T1", "T2"]
    assert payload["level_map"] == {"C7": 1, "T1": 2, "T2": 3}


def test_production_segmentation_stage_honors_existing_pipeline_run_device_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _enable_debug_segmentation_bundles(monkeypatch)
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    registry = SegmentationBundleRegistry(store, settings=settings)
    install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        settings=settings,
        activate=True,
        active_checkpoint_id="fold-0:checkpoint_final",
    )

    manifest.pipeline_runs.append(
        PipelineRun(
            stage="segmentation",
            status="running",
            backend_tool="nnunetv2",
            environment_id="nnunet-verse20-win",
            device="cpu",
            requested_device="cpu",
            effective_device="cpu",
            backend_health={"status": "ready"},
        )
    )

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    observed_devices: list[str] = []

    class FakeDriver:
        driver_id = "nnunetv2"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta
            observed_devices.append(device)
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            label_map[(0, 0, 0)] = runtime_model.label_mapping["C7"]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("python", "nnunet_predict_sidecar.py"),
                log_path=working_dir / "sidecar.log",
                device=device,
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    apply_stage_result(manifest, result)

    assert observed_devices == ["cpu"]
    assert manifest.pipeline_runs[-1].requested_device == "cpu"
    assert manifest.pipeline_runs[-1].effective_device == "cpu"


def test_active_bundle_switch_changes_gui_production_backend_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _enable_debug_segmentation_bundles(monkeypatch)
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    fold0_bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        settings=settings,
        activate=True,
        active_checkpoint_id="fold-0:checkpoint_final",
    )
    fold1_bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 1",
        settings=settings,
        activate=False,
        active_checkpoint_id="fold-1:checkpoint_latest",
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    class FakeDriver:
        driver_id = "nnunetv2"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta, device
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            label_map[(0, 0, 0)] = runtime_model.label_mapping["C7"]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("python", "nnunet_predict_sidecar.py"),
                log_path=working_dir / "sidecar.log",
                device="cuda",
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeDriver(),
    )

    fold0_result = run_segmentation_stage(store, manifest)
    fold0_payload = json.loads(Path(fold0_result.artifacts[0].path).read_text(encoding="utf-8"))
    registry.set_active_bundle_id(fold1_bundle.bundle_id)
    fold1_result = run_segmentation_stage(store, manifest)
    fold1_payload = json.loads(Path(fold1_result.artifacts[0].path).read_text(encoding="utf-8"))

    assert fold0_payload["model_bundle_id"] == fold0_bundle.bundle_id
    assert fold0_payload["resolved_checkpoint_id"] == "fold-0:checkpoint_final"
    assert fold1_payload["model_bundle_id"] == fold1_bundle.bundle_id
    assert fold1_payload["resolved_checkpoint_id"] == "fold-1:checkpoint_latest"


def test_production_segmentation_stage_supports_totalsegmentator_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    monkeypatch.setattr(
        bundles_module,
        "_resolve_totalsegmentator_executable",
        lambda: r"C:\tools\TotalSegmentator.exe",
    )
    monkeypatch.setattr(
        bundles_module,
        "_detect_totalsegmentator_version",
        lambda: "2.12.0",
    )
    bundle = install_totalsegmentator_bundle(
        store=store,
        bundle_id="TotalSegmentator Baseline",
        settings=settings,
        activate=True,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )

    class FakeTotalSegDriver:
        driver_id = "totalsegmentator"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta, device
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            label_map[(0, 0, 0)] = runtime_model.label_mapping["C7"]
            label_map[(0, 0, 1)] = runtime_model.label_mapping["T1"]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("TotalSegmentator.exe",),
                log_path=working_dir / "totalsegmentator.log",
                device="cuda",
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeTotalSegDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    payload = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))

    assert payload["model_bundle_id"] == bundle.bundle_id
    assert payload["driver_id"] == "totalsegmentator"
    assert payload["model_display_name"] == "TotalSegmentator Baseline"
    assert payload["resolved_checkpoint_id"] == "totalsegmentator-2.12.0"


def test_production_segmentation_stage_supports_skellytour_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store, manifest = _prepare_ct_case(
        tmp_path,
        segmentation_profile=SegmentationProfile.PRODUCTION.value,
    )
    settings = _settings_service(tmp_path)
    monkeypatch.setattr(
        bundles_module,
        "_resolve_skellytour_executable",
        lambda: r"C:\tools\skellytour.exe",
    )
    monkeypatch.setattr(
        bundles_module,
        "_detect_skellytour_version",
        lambda: "0.0.2",
    )
    bundle = install_skellytour_bundle(
        store=store,
        bundle_id="SkellyTour",
        settings=settings,
        activate=True,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="auto",
            effective_device="cpu",
            backend="cpu",
            cuda_version=None,
            gpu_name=None,
            total_vram_mb=None,
            backend_health={"status": "cpu-only"},
        ),
    )

    class FakeSkellyTourDriver:
        driver_id = "skellytour"

        def predict(
            self,
            normalized_volume_path: Path,
            runtime_model,
            working_dir: Path,
            *,
            device: str,
            continue_prediction: bool = False,
            disable_tta: bool = False,
        ) -> PredictionBatchResult:
            del continue_prediction, disable_tta, device
            staged_input_dir = working_dir / "inputs"
            prediction_dir = working_dir / "predictions"
            staged_input_dir.mkdir(parents=True, exist_ok=True)
            prediction_dir.mkdir(parents=True, exist_ok=True)

            case_id = normalized_volume_path.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}.nii.gz"
            staged_input_path.write_bytes(normalized_volume_path.read_bytes())

            image = nib.load(str(normalized_volume_path))
            label_map = np.zeros(np.asarray(image.dataobj).shape, dtype=np.int16)
            label_map[(0, 0, 0)] = runtime_model.label_mapping["C7"]
            label_map[(0, 0, 1)] = runtime_model.label_mapping["T1"]
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            nib.save(nib.Nifti1Image(label_map, image.affine), str(prediction_path))

            return PredictionBatchResult(
                working_dir=working_dir,
                staged_input_dir=staged_input_dir,
                prediction_dir=prediction_dir,
                command=("skellytour.exe",),
                log_path=working_dir / "skellytour.log",
                device="cpu",
                outputs=(
                    PredictionOutput(
                        case_id=case_id,
                        source_path=normalized_volume_path,
                        staged_input_path=staged_input_path,
                        prediction_path=prediction_path,
                    ),
                ),
                started_at_utc="2026-03-26T00:00:00Z",
                finished_at_utc="2026-03-26T00:00:05Z",
                stdout="prediction complete",
                stderr="",
            )

    monkeypatch.setattr(
        segmentation_module,
        "resolve_segmentation_driver",
        lambda driver_id, performance_policy=None: FakeSkellyTourDriver(),
    )

    result = run_segmentation_stage(store, manifest)
    payload = json.loads(Path(result.artifacts[0].path).read_text(encoding="utf-8"))

    assert payload["model_bundle_id"] == bundle.bundle_id
    assert payload["driver_id"] == "skellytour"
    assert payload["model_display_name"] == "SkellyTour High"
    assert payload["resolved_checkpoint_id"] == "skellytour-high-0.0.2"
