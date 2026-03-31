import json
from dataclasses import replace
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest
from PySide6.QtCore import QSettings

import spinelab.pipeline.orchestrator as orchestrator_module
import spinelab.pipeline.stage_registry as stage_registry_module
import spinelab.pipeline.stages.segmentation as segmentation_module
from spinelab.io import CaseStore
from spinelab.models import CaseManifest, SegmentationProfile
from spinelab.pipeline import PipelineOrchestrator
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.device import RuntimeDeviceSelection
from spinelab.segmentation import (
    DEBUG_SEGMENTATION_BUNDLES_ENV_VAR,
    PredictionBatchResult,
    PredictionOutput,
    SegmentationBundleRegistry,
    install_nnunet_bundle,
)
from spinelab.services import SettingsService
from spinelab.services.performance import performance_coordinator, reset_performance_coordinator


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "pipeline-orchestrator.ini"),
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
    (trainer_root / "plans.json").write_text("{}", encoding="utf-8")
    (trainer_root / "dataset.json").write_text("{}", encoding="utf-8")
    (trainer_root / "fold_0" / "checkpoint_final.pth").write_bytes(b"checkpoint")
    return trainer_root


def test_pipeline_orchestrator_generates_volume_metrics_and_findings(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Pipeline Case"
    manifest.cobb_angle = "42 deg"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "ct_volume.nii.gz"
    volume_data = np.arange(27, dtype=np.int16).reshape((3, 3, 3))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.5, 1.5, 2.0, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    orchestrator = PipelineOrchestrator(store)
    updated_manifest = orchestrator.submit_case_analysis(manifest, preferred_device="cpu")

    completed_runs = updated_manifest.pipeline_runs[-8:]
    assert [run.stage for run in completed_runs] == [
        "ingest",
        "normalize",
        "segmentation",
        "mesh",
        "landmarks",
        "registration",
        "measurements",
        "findings",
    ]
    assert all(run.status == "complete" for run in completed_runs)
    assert all(run.device == "cpu" for run in completed_runs)
    assert updated_manifest.volumes
    assert updated_manifest.volumes[0].dimensions == (3, 3, 3)
    assert updated_manifest.volumes[0].voxel_spacing == (1.5, 1.5, 2.0)
    assert updated_manifest.measurements.records
    assert "Cobb Angle" in updated_manifest.measurements.values
    assert updated_manifest.findings
    assert any(asset.kind == "mesh_3d" for asset in updated_manifest.assets)
    assert any(artifact.artifact_type == "segmentation" for artifact in updated_manifest.artifacts)
    assert any(artifact.artifact_type == "measurements" for artifact in updated_manifest.artifacts)
    assert all(Path(artifact.path).exists() for artifact in updated_manifest.artifacts)
    assert store.case_is_editable(updated_manifest.case_id) is True


def test_pipeline_orchestrator_materializes_external_case_ids(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.case_id = "external::sample_case"
    manifest.patient_name = "External Pipeline Case"
    manifest.cobb_angle = "12 deg"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "external_ct_volume.nii.gz"
    volume_data = np.arange(27, dtype=np.int16).reshape((3, 3, 3))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 1.0, 1.0])), str(volume_path))
    import_manifest = CaseManifest.blank()
    asset = store.import_asset(import_manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assets = import_manifest.assets
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    orchestrator = PipelineOrchestrator(store)
    updated_manifest = orchestrator.submit_case_analysis(manifest, preferred_device="cpu")

    assert updated_manifest.case_id.startswith("case-sample-case-")
    assert updated_manifest.case_id != manifest.case_id
    assert store.case_is_editable(updated_manifest.case_id) is True
    assert any(run.stage == "segmentation" for run in updated_manifest.pipeline_runs)


def test_pipeline_orchestrator_reports_stage_progress(tmp_path: Path) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Progress Case"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "progress_ct_volume.nii.gz"
    volume_data = np.arange(27, dtype=np.int16).reshape((3, 3, 3))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 1.0, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    events = []
    orchestrator = PipelineOrchestrator(store)
    orchestrator.submit_case_analysis(
        manifest,
        preferred_device="cpu",
        progress_callback=events.append,
    )

    assert events[0].stage.value == "ingest"
    assert events[0].stage_index == 1
    assert events[0].total_stages == 8
    assert events[0].status == "running"
    assert events[1].stage.value == "ingest"
    assert events[1].status == "complete"
    assert events[-2].stage.value == "findings"
    assert events[-2].status == "running"
    assert events[-1].stage.value == "findings"
    assert events[-1].status == "complete"
    assert all(
        later.percent >= earlier.percent
        for earlier, later in zip(events, events[1:], strict=False)
    )
    assert events[-1].percent == 100
    segmentation_running_events = [
        event
        for event in events
        if event.stage == PipelineStageName.SEGMENTATION and event.status == "running"
    ]
    assert len(events) >= 16
    assert len(segmentation_running_events) > 1
    assert any(event.stage_fraction > 0.0 for event in segmentation_running_events)


def test_pipeline_orchestrator_runs_happy_path_with_production_segmentation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR, "1")
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Production Pipeline Case"
    manifest.cobb_angle = "31 deg"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.PRODUCTION.value

    volume_path = tmp_path / "production_ct_volume.nii.gz"
    volume_data = np.arange(64, dtype=np.int16).reshape((4, 4, 4))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.2, 1.2, 2.5, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

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
    runtime_selection = RuntimeDeviceSelection(
        requested_device="cuda",
        effective_device="cuda",
        backend="nvidia-cuda",
        cuda_version="12.4",
        gpu_name="Test GPU",
        total_vram_mb=81920,
        backend_health={"status": "ready"},
    )

    monkeypatch.setattr(
        segmentation_module,
        "SegmentationBundleRegistry",
        lambda current_store: registry,
    )
    monkeypatch.setattr(
        segmentation_module,
        "choose_runtime_device",
        lambda preferred_device=None: runtime_selection,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "choose_runtime_device",
        lambda preferred_device=None: runtime_selection,
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

    orchestrator = PipelineOrchestrator(store)
    updated_manifest = orchestrator.submit_case_analysis(manifest, preferred_device="cuda")

    assert updated_manifest.measurements.records
    assert updated_manifest.findings
    assert any(
        artifact.artifact_type == "segmentation-run-manifest"
        for artifact in updated_manifest.artifacts
    )
    segmentation_run = next(
        run for run in updated_manifest.pipeline_runs if run.stage == "segmentation"
    )
    assert segmentation_run.backend_tool == "nnunetv2"
    assert segmentation_run.environment_id == bundle.environment_id
    assert segmentation_run.device == "cuda"
    assert segmentation_run.effective_device == "cuda"


def test_pipeline_orchestrator_failed_stage_never_reports_100_percent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()
    manifest.patient_name = "Failing Progress Case"
    manifest.comparison_modalities = {"primary": "ct", "secondary": "xray"}
    manifest.segmentation_profile = SegmentationProfile.SCAFFOLD.value

    volume_path = tmp_path / "failing_progress_ct_volume.nii.gz"
    volume_data = np.arange(27, dtype=np.int16).reshape((3, 3, 3))
    nib.save(nib.Nifti1Image(volume_data, np.diag([1.0, 1.0, 1.0, 1.0])), str(volume_path))

    asset = store.import_asset(manifest, volume_path, kind="ct_zstack", label="CT")
    manifest.assign_asset_to_role(asset.asset_id, "ct_stack")

    original_get_stage_spec = stage_registry_module.get_stage_spec

    def failing_segmentation_runner(
        current_store,
        current_manifest,
        *,
        progress_callback=None,
        performance_policy=None,
    ):
        del current_store, current_manifest, performance_policy
        if progress_callback is not None:
            progress_callback(1.0, "Prediction export complete")
        raise RuntimeError("segmentation failed")

    def patched_get_stage_spec(stage: PipelineStageName):
        spec = original_get_stage_spec(stage)
        if stage == PipelineStageName.SEGMENTATION:
            return replace(spec, runner=failing_segmentation_runner)
        return spec

    monkeypatch.setattr(orchestrator_module, "get_stage_spec", patched_get_stage_spec)

    events = []
    orchestrator = PipelineOrchestrator(store)
    with pytest.raises(RuntimeError, match="segmentation failed"):
        orchestrator.submit_case_analysis(
            manifest,
            preferred_device="cpu",
            requested_stages=(PipelineStageName.SEGMENTATION,),
            progress_callback=events.append,
        )

    assert events[-1].stage == PipelineStageName.SEGMENTATION
    assert events[-1].status == "failed"
    assert events[-1].percent < 100


def test_pipeline_orchestrator_traces_run_start_policy_even_if_mode_changes_mid_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reset_performance_coordinator()
    settings = _settings_service(tmp_path)
    settings.save_performance_mode("adaptive")
    coordinator = performance_coordinator(settings)
    coordinator.set_mode("adaptive")

    store = CaseStore(tmp_path / "data-root")
    manifest = CaseManifest.blank()

    original_get_stage_spec = stage_registry_module.get_stage_spec

    def ingest_runner(current_store, current_manifest) -> StageExecutionResult:
        del current_store, current_manifest
        performance_coordinator(settings).set_mode("turbo")
        return StageExecutionResult(
            stage=PipelineStageName.INGEST,
            status="complete",
            message="Ingest complete.",
        )

    def patched_get_stage_spec(stage: PipelineStageName):
        spec = original_get_stage_spec(stage)
        if stage == PipelineStageName.INGEST:
            return replace(spec, runner=ingest_runner)
        return spec

    monkeypatch.setattr(orchestrator_module, "get_stage_spec", patched_get_stage_spec)

    orchestrator = PipelineOrchestrator(store, settings=settings)
    updated_manifest = orchestrator.submit_case_analysis(
        manifest,
        preferred_device="cpu",
        requested_stages=(PipelineStageName.INGEST,),
    )

    ingest_run = updated_manifest.pipeline_runs[-1]
    trace_payload = json.loads(Path(ingest_run.performance_trace_path).read_text("utf-8"))
    assert trace_payload["performance_mode"] == "adaptive"
    assert trace_payload["performance_policy"]["mode"] == "adaptive"
    assert performance_coordinator(settings).active_mode.value == "turbo"
    reset_performance_coordinator()
