from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from spinelab.io import EXTERNAL_CASE_PREFIX, CaseStore
from spinelab.models import CaseManifest, PipelineRun
from spinelab.models.manifest import utc_now
from spinelab.pipeline.artifacts import performance_trace_path, stage_root, write_json_artifact
from spinelab.pipeline.backends import BACKEND_ADAPTERS, ENVIRONMENT_SPECS
from spinelab.pipeline.contracts import PipelineStageName
from spinelab.pipeline.device import choose_runtime_device
from spinelab.pipeline.manifest_bridge import apply_stage_result, reset_stage_state
from spinelab.pipeline.stage_registry import (
    DEFAULT_ANALYSIS_SEQUENCE,
    downstream_stages,
    expand_requested_stages,
    get_stage_spec,
)
from spinelab.services import configure_runtime_policy
from spinelab.services.performance import ResolvedPerformancePolicy

if TYPE_CHECKING:
    from spinelab.services.settings_service import SettingsService

ANALYSIS_STAGE_SEQUENCE = DEFAULT_ANALYSIS_SEQUENCE

_STAGE_PROGRESS_WEIGHTS: dict[PipelineStageName, float] = {
    PipelineStageName.INGEST: 2.0,
    PipelineStageName.NORMALIZE: 4.0,
    PipelineStageName.SEGMENTATION: 46.0,
    PipelineStageName.MESH: 16.0,
    PipelineStageName.LANDMARKS: 10.0,
    PipelineStageName.REGISTRATION: 8.0,
    PipelineStageName.MEASUREMENTS: 10.0,
    PipelineStageName.FINDINGS: 4.0,
}


@dataclass(frozen=True, slots=True)
class AnalysisProgressEvent:
    stage: PipelineStageName
    stage_index: int
    total_stages: int
    status: str
    detail: str
    percent: float
    stage_fraction: float

    @property
    def stage_percent(self) -> float:
        return self.stage_fraction * 100.0


AnalysisProgressUpdate = AnalysisProgressEvent


StageProgressCallback = Callable[[AnalysisProgressEvent], None]
SegmentationSubprogressCallback = Callable[[float, str], None]


class PipelineOrchestrator:
    def __init__(
        self,
        store: CaseStore,
        *,
        settings: SettingsService | None = None,
    ) -> None:
        self._store = store
        self._settings = settings

    def submit_case_analysis(
        self,
        manifest: CaseManifest,
        *,
        preferred_device: str | None = None,
        requested_stages: tuple[PipelineStageName, ...] | None = None,
        progress_callback: StageProgressCallback | None = None,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
    ) -> CaseManifest:
        editable_manifest = self._ensure_editable_manifest(manifest)
        resolved_policy = configure_runtime_policy(settings=self._settings)
        selection = choose_runtime_device(preferred_device)
        stages = expand_requested_stages(requested_stages)
        invalidated: set[PipelineStageName] = set()
        total_stages = len(stages)
        stage_weights = {
            stage: _STAGE_PROGRESS_WEIGHTS.get(stage, 1.0) for stage in stages
        }
        total_weight = max(sum(stage_weights.values()), 1.0)
        completed_weight = 0.0
        last_percent = 0.0

        for index, stage in enumerate(stages, start=1):
            affected_stages = downstream_stages(stage)
            if affected_stages[0] not in invalidated:
                self._reset_stage_state(editable_manifest, affected_stages)
                invalidated.update(affected_stages)

            spec = get_stage_spec(stage)
            backend_health = self._resolve_backend_health(stage, selection)
            stage_progress = 0.0
            stage_key = stage
            stage_index = index
            stage_weight = stage_weights[stage]
            completed_weight_before_stage = completed_weight

            def emit_progress(
                status: str,
                detail: str,
                *,
                stage_fraction: float,
                _completed_weight_before_stage: float = completed_weight_before_stage,
                _stage_weight: float = stage_weight,
                _stage_key: PipelineStageName = stage_key,
                _stage_index: int = stage_index,
            ) -> None:
                nonlocal last_percent
                if progress_callback is None:
                    return
                normalized_fraction = max(0.0, min(1.0, float(stage_fraction)))
                normalized_status = status.strip().lower()
                if normalized_status == "running":
                    normalized_fraction = min(normalized_fraction, 0.999)
                raw_percent = (
                    (_completed_weight_before_stage + (_stage_weight * normalized_fraction))
                    / total_weight
                ) * 100.0
                allows_full_completion = (
                    normalized_status == "complete"
                    and _stage_index == total_stages
                    and normalized_fraction >= 1.0
                )
                max_percent = 100.0 if allows_full_completion else 99.0
                resolved_percent = max(last_percent, min(raw_percent, max_percent))
                progress_callback(
                    AnalysisProgressEvent(
                        stage=_stage_key,
                        stage_index=_stage_index,
                        total_stages=total_stages,
                        status=status,
                        detail=detail,
                        percent=resolved_percent,
                        stage_fraction=normalized_fraction,
                    )
                )
                last_percent = resolved_percent

            def segmentation_progress_callback(fraction: float, detail: str) -> None:
                nonlocal stage_progress
                stage_progress = max(stage_progress, max(0.0, min(1.0, float(fraction))))
                emit_progress("running", detail, stage_fraction=stage_progress)

            emit_progress("running", spec.description, stage_fraction=0.0)
            pipeline_run = PipelineRun(
                stage=stage.value,
                status="running",
                backend_tool=spec.backend_tool,
                environment_id=spec.environment_id,
                device=selection.device,
                requested_device=selection.requested_device,
                effective_device=selection.effective_device,
                cuda_version=selection.cuda_version,
                gpu_name=selection.gpu_name,
                total_vram_mb=selection.total_vram_mb,
                backend_health=backend_health,
                tool_version="0.2.0",
                fallback_reason=selection.fallback_reason,
                inputs=self._stage_inputs(editable_manifest, stage),
                message=f"Running {stage.value}.",
            )
            editable_manifest.pipeline_runs.append(pipeline_run)
            self._store.save_manifest(editable_manifest)
            started_at = time.perf_counter()
            try:
                if stage == PipelineStageName.SEGMENTATION:
                    result = spec.runner(
                        self._store,
                        editable_manifest,
                        progress_callback=segmentation_progress_callback,
                        performance_policy=resolved_policy,
                        disable_tta=disable_tta,
                        tile_step_size=tile_step_size,
                    )
                else:
                    result = spec.runner(self._store, editable_manifest)
            except Exception as exc:
                elapsed_seconds = time.perf_counter() - started_at
                pipeline_run.status = "failed"
                pipeline_run.error_text = str(exc)
                pipeline_run.message = f"{stage.value.title()} failed."
                pipeline_run.finished_at = utc_now()
                pipeline_run.timings = {"stage_total_seconds": round(elapsed_seconds, 6)}
                pipeline_run.performance_trace_path = str(
                    self._write_stage_performance_trace(
                        editable_manifest,
                        pipeline_run,
                        performance_policy=resolved_policy,
                        warnings=(),
                    )
                )
                self._store.save_manifest(editable_manifest)
                emit_progress("failed", str(exc), stage_fraction=stage_progress)
                raise
            apply_stage_result(editable_manifest, result)
            elapsed_seconds = time.perf_counter() - started_at
            pipeline_run.backend_health = self._resolve_backend_health_for_backend(
                backend_tool=pipeline_run.backend_tool,
                environment_id=pipeline_run.environment_id,
                selection=selection,
            )
            pipeline_run.status = result.status
            pipeline_run.outputs = list(result.outputs)
            pipeline_run.message = result.message
            pipeline_run.finished_at = utc_now()
            pipeline_run.timings = {
                **result.timings,
                "stage_total_seconds": round(elapsed_seconds, 6),
            }
            pipeline_run.performance_trace_path = str(
                self._write_stage_performance_trace(
                    editable_manifest,
                    pipeline_run,
                    performance_policy=resolved_policy,
                    warnings=result.warnings,
                )
            )
            self._store.save_manifest(editable_manifest)
            emit_progress(result.status, result.message, stage_fraction=1.0)
            completed_weight += stage_weights[stage]
        return editable_manifest

    def _ensure_editable_manifest(self, manifest: CaseManifest) -> CaseManifest:
        if self._store.case_is_editable(manifest.case_id):
            self._store.save_manifest(manifest)
            return manifest
        editable_manifest = CaseManifest.from_dict(manifest.to_dict())
        editable_manifest.case_id = _editable_case_id(manifest.case_id)
        session = self._store.session_store.create_blank_session(manifest=editable_manifest)
        self._store.activate_session(session)
        self._store.save_manifest(editable_manifest)
        return editable_manifest

    def _reset_stage_state(
        self,
        manifest: CaseManifest,
        stages: tuple[PipelineStageName, ...],
    ) -> None:
        reset_stage_state(manifest, stages)
        for stage in stages:
            root = stage_root(self._store, manifest, stage.value)
            if root.exists():
                shutil.rmtree(root, ignore_errors=True)

    def _stage_inputs(self, manifest: CaseManifest, stage: PipelineStageName) -> list[str]:
        if stage == PipelineStageName.INGEST:
            return [asset.managed_path for asset in manifest.assets if asset.kind != "mesh_3d"]
        if stage == PipelineStageName.NORMALIZE:
            return [
                asset.managed_path
                for asset in manifest.assets
                if asset.kind in {"ct_zstack", "mri_2d"}
            ]
        stage_dependencies = get_stage_spec(stage).dependencies
        dependency_values = {dependency.value for dependency in stage_dependencies}
        artifact_inputs = [
            artifact.path
            for artifact in manifest.artifacts
            if artifact.stage in dependency_values
        ]
        if stage == PipelineStageName.REGISTRATION:
            artifact_inputs.extend(
                asset.managed_path
                for asset in manifest.assets
                if asset.processing_role in {"xray_ap", "xray_lat"}
            )
        return artifact_inputs

    def _resolve_backend_health(
        self,
        stage: PipelineStageName,
        selection,
    ) -> dict[str, str]:
        spec = get_stage_spec(stage)
        return self._resolve_backend_health_for_backend(
            backend_tool=spec.backend_tool,
            environment_id=spec.environment_id,
            selection=selection,
        )

    def _resolve_backend_health_for_backend(
        self,
        *,
        backend_tool: str,
        environment_id: str,
        selection,
    ) -> dict[str, str]:
        if backend_tool == "internal":
            return {
                **selection.backend_health,
                "status": "ready",
                "mode": "internal",
            }
        adapter = next(
            (
                candidate
                for candidate in BACKEND_ADAPTERS
                if candidate.spec.tool_name == backend_tool
            ),
            None,
        )
        if adapter is None:
            return {
                **selection.backend_health,
                "status": "unknown-backend",
                "backend_tool": backend_tool,
            }
        backend_spec = adapter.spec
        environment_spec = next(
            (
                candidate
                for candidate in ENVIRONMENT_SPECS
                if candidate.env_id == environment_id
            ),
            None,
        )
        environment_manifest = (
            str(environment_spec.manifest_path) if environment_spec is not None else ""
        )
        env_manifest_present = (
            environment_spec is not None and environment_spec.manifest_path.exists()
        )
        status = selection.backend_health.get("status", "ready")
        if backend_spec.required_device.value == "cuda" and selection.effective_device != "cuda":
            status = "device-unavailable"
        return {
            **selection.backend_health,
            "status": status,
            "backend_tool": backend_spec.tool_name,
            "required_device": backend_spec.required_device.value,
            "platform_mode": backend_spec.platform_mode.value,
            "environment_id": environment_id,
            "environment_manifest": environment_manifest,
            "environment_manifest_present": str(env_manifest_present).lower(),
        }

    def _write_stage_performance_trace(
        self,
        manifest: CaseManifest,
        pipeline_run: PipelineRun,
        *,
        performance_policy: ResolvedPerformancePolicy,
        warnings: tuple[str, ...] | list[str],
    ):
        trace_path = performance_trace_path(self._store, manifest, pipeline_run.stage)
        write_json_artifact(
            trace_path,
            {
                "run_id": pipeline_run.run_id,
                "stage": pipeline_run.stage,
                "status": pipeline_run.status,
                "requested_device": pipeline_run.requested_device,
                "effective_device": pipeline_run.effective_device,
                "gpu_name": pipeline_run.gpu_name,
                "total_vram_mb": pipeline_run.total_vram_mb,
                "cuda_version": pipeline_run.cuda_version,
                "backend_tool": pipeline_run.backend_tool,
                "environment_id": pipeline_run.environment_id,
                "backend_health": pipeline_run.backend_health,
                "performance_mode": performance_policy.mode.value,
                "performance_policy": {
                    "name": performance_policy.name,
                    "mode": performance_policy.mode.value,
                    "vtk_smp_backend": performance_policy.vtk_smp_backend,
                    "cpu_heavy_workers": performance_policy.cpu_heavy_workers,
                    "io_workers": performance_policy.io_workers,
                    "render_workers": performance_policy.render_workers,
                    "preview_decode_workers": performance_policy.preview_decode_workers,
                    "lod_prewarm_workers": performance_policy.lod_prewarm_workers,
                    "nnunet_preprocess_workers": performance_policy.nnunet_preprocess_workers,
                    "nnunet_export_workers": performance_policy.nnunet_export_workers,
                    "blas_threads": performance_policy.blas_threads,
                    "image_cache_budget_bytes": performance_policy.image_cache_budget_bytes,
                    "raw_mesh_cache_budget_bytes": performance_policy.raw_mesh_cache_budget_bytes,
                    "lod_mesh_cache_budget_bytes": performance_policy.lod_mesh_cache_budget_bytes,
                    "active_volume_cache_budget_bytes": (
                        performance_policy.active_volume_cache_budget_bytes
                    ),
                },
                "fallback_reason": pipeline_run.fallback_reason,
                "inputs": pipeline_run.inputs,
                "outputs": pipeline_run.outputs,
                "timings": pipeline_run.timings,
                "warnings": list(warnings),
                "started_at": pipeline_run.started_at,
                "finished_at": pipeline_run.finished_at,
                "error_text": pipeline_run.error_text,
            },
        )
        return trace_path


def _editable_case_id(case_id: str) -> str:
    normalized = case_id.removeprefix(EXTERNAL_CASE_PREFIX)
    normalized = "".join(
        character.lower() if character.isalnum() else "-"
        for character in normalized.strip()
    ).strip("-")
    if not normalized:
        normalized = "analysis"
    return f"case-{normalized}-{uuid4().hex[:6]}"
