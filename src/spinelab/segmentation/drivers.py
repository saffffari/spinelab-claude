from __future__ import annotations

import os
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Protocol, cast

import nibabel as nib
import numpy as np

from spinelab.models.manifest import utc_now
from spinelab.segmentation.bundles import (
    CompositeSubModelSpec,
    SegmentationBundleCheckpoint,
    SegmentationBundleInferenceSpec,
    SegmentationRuntimeModel,
)
from spinelab.segmentation.process_control import run_tracked_segmentation_subprocess
from spinelab.services.performance import PerformancePolicy, active_performance_policy

DriverProgressCallback = Callable[[float, str], None]

DRIVER_ID_NNUNETV2 = "nnunetv2"
DRIVER_ID_CADS_COMPOSITE = "cads-composite"
DEFAULT_NNUNET_CONDA_ENV_NAME = "spinelab-nnunet"
_ENVIRONMENT_ID_TO_CONDA_ENV = {
    "cads-nnunet-win": DEFAULT_NNUNET_CONDA_ENV_NAME,
}


def _sidecar_entrypoint_path() -> Path:
    return Path(__file__).resolve().parents[3] / "tools" / "nnunet_predict_sidecar.py"


def conda_env_name_for_environment_id(environment_id: str) -> str:
    return _ENVIRONMENT_ID_TO_CONDA_ENV.get(environment_id, environment_id)


def _copy_file_or_hardlink(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _resolve_conda_executable() -> str | None:
    conda_executable = os.environ.get("CONDA_EXE")
    if conda_executable:
        candidate = Path(conda_executable)
        if candidate.exists():
            return str(candidate)
    return shutil.which("conda")


def _candidate_conda_roots(conda_executable: str) -> tuple[Path, ...]:
    resolved = Path(conda_executable).resolve()
    parents: list[Path] = []
    if resolved.parent.name.lower() in {"scripts", "condabin"}:
        parents.append(resolved.parent.parent)
    parents.append(resolved.parent)
    ordered: list[Path] = []
    seen: set[Path] = set()
    for candidate in parents:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return tuple(ordered)


def _resolve_env_python_executable(
    *,
    conda_executable: str,
    conda_env_name: str,
) -> Path | None:
    for root in _candidate_conda_roots(conda_executable):
        base_python = root / "python.exe"
        if root.name.lower() == conda_env_name.lower() and base_python.exists():
            return base_python
        env_python = root / "envs" / conda_env_name / "python.exe"
        if env_python.exists():
            return env_python
    return None


def _environment_python_command(environment_id: str) -> tuple[str, ...] | None:
    conda_executable = _resolve_conda_executable()
    if conda_executable is None:
        return None
    conda_env_name = conda_env_name_for_environment_id(environment_id)
    env_python_executable = _resolve_env_python_executable(
        conda_executable=conda_executable,
        conda_env_name=conda_env_name,
    )
    if env_python_executable is not None:
        return (str(env_python_executable),)
    return (conda_executable, "run", "-n", conda_env_name, "python")


def _environment_command(
    environment_id: str,
    *,
    executable_names: tuple[str, ...],
) -> tuple[str, ...] | None:
    conda_executable = _resolve_conda_executable()
    conda_env_name = conda_env_name_for_environment_id(environment_id)
    if conda_executable is not None:
        env_python_executable = _resolve_env_python_executable(
            conda_executable=conda_executable,
            conda_env_name=conda_env_name,
        )
        if env_python_executable is not None:
            env_root = env_python_executable.parent
            for executable_name in executable_names:
                candidates = (
                    env_root / "Scripts" / executable_name,
                    env_root / "Scripts" / f"{executable_name}.exe",
                    env_root / executable_name,
                    env_root / f"{executable_name}.exe",
                )
                for candidate in candidates:
                    if candidate.exists():
                        return (str(candidate),)
        return (conda_executable, "run", "-n", conda_env_name, executable_names[0])
    for executable_name in executable_names:
        for candidate_path in (
            shutil.which(executable_name),
            shutil.which(f"{executable_name}.exe"),
        ):
            if candidate_path:
                return (candidate_path,)
    return None


def _read_log_tail(log_path: Path, *, max_lines: int = 200, max_chars: int = 32768) -> str:
    tail_lines: deque[str] = deque(maxlen=max_lines)
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            tail_lines.append(line.rstrip("\n"))
    text = "\n".join(tail_lines)
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _remap_prediction_labels(
    *,
    raw_prediction_path: Path,
    prediction_path: Path,
    runtime_model: SegmentationRuntimeModel,
    source_level_map: dict[str, int],
    driver_label: str,
) -> None:
    image = cast(nib.Nifti1Image, nib.load(str(raw_prediction_path)))
    raw_data = np.asarray(image.dataobj, dtype=np.int16)
    remapped = np.zeros(raw_data.shape, dtype=np.int16)
    mapped_levels = 0
    for level_id, target_label in runtime_model.label_mapping.items():
        source_label = source_level_map.get(level_id)
        if source_label is None:
            continue
        if np.any(raw_data == source_label):
            remapped[raw_data == source_label] = int(target_label)
            mapped_levels += 1
    if mapped_levels == 0:
        raise SegmentationDriverError(
            f"{driver_label} completed, but none of the supported canonical vertebral "
            "levels could be mapped into the SpineLab label contract."
        )
    nib.save(
        nib.Nifti1Image(remapped.astype(np.int16), image.affine, image.header),
        str(prediction_path),
    )


@dataclass(frozen=True, slots=True)
class PredictionOutput:
    case_id: str
    source_path: Path
    staged_input_path: Path
    prediction_path: Path
    diagnostics_path: Path | None = None


@dataclass(frozen=True, slots=True)
class PredictionBatchResult:
    working_dir: Path
    staged_input_dir: Path
    prediction_dir: Path
    command: tuple[str, ...]
    log_path: Path | None
    device: str
    outputs: tuple[PredictionOutput, ...]
    started_at_utc: str
    finished_at_utc: str
    stdout: str
    stderr: str


class SegmentationDriverError(RuntimeError):
    pass


class SegmentationModelDriver(Protocol):
    driver_id: str

    def predict(
        self,
        normalized_volume_path: Path,
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult: ...

    def predict_batch(
        self,
        normalized_volume_paths: tuple[Path, ...],
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult: ...


class NNUNetV2SegmentationDriver:
    driver_id = DRIVER_ID_NNUNETV2

    def __init__(self, *, preprocessing_workers: int = 2, export_workers: int = 2) -> None:
        self._preprocessing_workers = preprocessing_workers
        self._export_workers = export_workers

    def predict(
        self,
        normalized_volume_path: Path,
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult:
        return self.predict_batch(
            (normalized_volume_path,),
            runtime_model,
            working_dir,
            device=device,
            continue_prediction=continue_prediction,
            disable_tta=disable_tta,
            tile_step_size=tile_step_size,
            progress_callback=progress_callback,
        )

    def predict_batch(
        self,
        normalized_volume_paths: tuple[Path, ...],
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult:
        if runtime_model.driver_id != self.driver_id:
            raise SegmentationDriverError(
                f"Runtime model {runtime_model.model_id} uses driver {runtime_model.driver_id!r}, "
                f"not {self.driver_id!r}."
            )
        conda_executable = _resolve_conda_executable()
        if conda_executable is None:
            raise SegmentationDriverError(
                "Unable to locate conda. The production nnU-Net sidecar requires conda run."
            )
        if not runtime_model.checkpoint_path.exists():
            raise SegmentationDriverError(
                f"Resolved checkpoint is missing: {runtime_model.checkpoint_path}"
            )
        if not runtime_model.runtime_results_root.exists():
            raise SegmentationDriverError(
                f"Resolved nnU-Net results root is missing: {runtime_model.runtime_results_root}"
            )
        sidecar_entrypoint = _sidecar_entrypoint_path()
        if not sidecar_entrypoint.exists():
            raise SegmentationDriverError(
                f"Production nnU-Net sidecar entrypoint is missing: {sidecar_entrypoint}"
            )

        staged_input_dir = working_dir / "inputs"
        prediction_dir = working_dir / "predictions"
        if staged_input_dir.exists():
            shutil.rmtree(staged_input_dir)
        if prediction_dir.exists() and not continue_prediction:
            shutil.rmtree(prediction_dir)
        staged_input_dir.mkdir(parents=True, exist_ok=True)
        prediction_dir.mkdir(parents=True, exist_ok=True)

        staged_outputs: list[PredictionOutput] = []
        used_case_ids: set[str] = set()
        for input_path in normalized_volume_paths:
            resolved_input = input_path.resolve()
            if not resolved_input.exists():
                raise SegmentationDriverError(
                    f"Normalized input volume is missing: {resolved_input}"
                )
            case_id = resolved_input.name.removesuffix(".nii.gz").removesuffix(".nii")
            if case_id in used_case_ids:
                raise SegmentationDriverError(
                    f"Duplicate staged inference case id {case_id!r} under {working_dir}."
                )
            used_case_ids.add(case_id)
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            _copy_file_or_hardlink(resolved_input, staged_input_path)
            staged_outputs.append(
                PredictionOutput(
                    case_id=case_id,
                    source_path=resolved_input,
                    staged_input_path=staged_input_path,
                    prediction_path=prediction_dir / f"{case_id}.nii.gz",
                    diagnostics_path=prediction_dir / f"{case_id}.diagnostics.json",
                )
            )

        conda_env_name = conda_env_name_for_environment_id(runtime_model.environment_id)
        env_python_executable = _resolve_env_python_executable(
            conda_executable=conda_executable,
            conda_env_name=conda_env_name,
        )
        runtime_model.runtime_raw_root.mkdir(parents=True, exist_ok=True)
        runtime_model.runtime_preprocessed_root.mkdir(parents=True, exist_ok=True)
        model_dir = runtime_model.runtime_results_root / (
            f"Dataset{runtime_model.inference_spec.dataset_id:03d}_"
            f"{runtime_model.inference_spec.dataset_name}"
        ) / (
            f"{runtime_model.inference_spec.trainer_name}"
            f"__{runtime_model.inference_spec.plan_name}"
            f"__{runtime_model.inference_spec.configuration}"
        )
        command_prefix = (
            (str(env_python_executable),)
            if env_python_executable is not None
            else (
                conda_executable,
                "run",
                "-n",
                conda_env_name,
                "python",
            )
        )
        command = command_prefix + (
            str(sidecar_entrypoint),
            "--model-dir",
            str(model_dir),
            "--input-dir",
            str(staged_input_dir),
            "--output-dir",
            str(prediction_dir),
            "--results-root",
            str(runtime_model.runtime_results_root),
            "--raw-root",
            str(runtime_model.runtime_raw_root),
            "--preprocessed-root",
            str(runtime_model.runtime_preprocessed_root),
            "--fold",
            runtime_model.checkpoint.fold,
            "--checkpoint",
            runtime_model.checkpoint.checkpoint_name,
            "--device",
            device,
            "--npp",
            str(self._preprocessing_workers),
            "--nps",
            str(self._export_workers),
        )
        command_list = list(command)
        if disable_tta:
            command_list.append("--disable_tta")
        if continue_prediction:
            command_list.append("--continue_prediction")
        if tile_step_size != 0.5:
            command_list.extend(["--tile_step_size", str(tile_step_size)])
        environment = os.environ.copy()
        environment["nnUNet_results"] = str(runtime_model.runtime_results_root)
        environment["nnUNet_raw"] = str(runtime_model.runtime_raw_root)
        environment["nnUNet_preprocessed"] = str(runtime_model.runtime_preprocessed_root)
        log_path = working_dir / "sidecar.log"
        started_at_utc = utc_now()
        with log_path.open("w", encoding="utf-8", errors="replace") as log_handle:
            completed = run_tracked_segmentation_subprocess(
                command_list,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
                check=False,
                label="nnunet-sidecar-predict",
            )
        finished_at_utc = utc_now()
        log_excerpt = _read_log_tail(log_path) if log_path.exists() else ""
        if completed.returncode != 0:
            raise SegmentationDriverError(
                "nnU-Net sidecar prediction failed with exit code "
                f"{completed.returncode}.\nsidecar_log:\n{log_path}\noutput_tail:\n{log_excerpt}"
            )
        missing_predictions = [
            output.prediction_path
            for output in staged_outputs
            if not output.prediction_path.exists()
        ]
        if missing_predictions:
            raise SegmentationDriverError(
                "nnU-Net sidecar completed without writing expected predictions:\n"
                + "\n".join(str(path) for path in missing_predictions)
            )
        return PredictionBatchResult(
            working_dir=working_dir,
            staged_input_dir=staged_input_dir,
            prediction_dir=prediction_dir,
            command=tuple(command_list),
            log_path=log_path,
            device=device,
            outputs=tuple(staged_outputs),
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            stdout=log_excerpt,
            stderr="",
        )


class CADSCompositeSegmentationDriver:
    """Runs multiple CADS nnU-Net task models and merges their predictions."""

    driver_id = DRIVER_ID_CADS_COMPOSITE

    def __init__(self, *, preprocessing_workers: int = 2, export_workers: int = 2) -> None:
        self._inner_driver = NNUNetV2SegmentationDriver(
            preprocessing_workers=preprocessing_workers,
            export_workers=export_workers,
        )

    def predict(
        self,
        normalized_volume_path: Path,
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult:
        return self.predict_batch(
            (normalized_volume_path,),
            runtime_model,
            working_dir,
            device=device,
            continue_prediction=continue_prediction,
            disable_tta=disable_tta,
            tile_step_size=tile_step_size,
            progress_callback=progress_callback,
        )

    def predict_batch(
        self,
        normalized_volume_paths: tuple[Path, ...],
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
        tile_step_size: float = 0.5,
        progress_callback: DriverProgressCallback | None = None,
    ) -> PredictionBatchResult:
        if not runtime_model.sub_models:
            raise SegmentationDriverError(
                f"Composite driver requires sub_models but bundle {runtime_model.model_id} has none."
            )

        started_at_utc = utc_now()
        all_task_results: list[tuple[CompositeSubModelSpec, PredictionBatchResult]] = []
        total_sub_models = len(runtime_model.sub_models)

        for sub_model_index, sub_model_spec in enumerate(runtime_model.sub_models):
            if progress_callback is not None:
                progress_callback(
                    sub_model_index / total_sub_models,
                    f"Task {sub_model_index + 1}/{total_sub_models}: {sub_model_spec.dataset_name}",
                )
            task_working_dir = working_dir / f"task_{sub_model_spec.dataset_name}"
            task_runtime_model = _build_sub_runtime_model(
                parent=runtime_model,
                spec=sub_model_spec,
            )
            result = self._inner_driver.predict_batch(
                normalized_volume_paths,
                task_runtime_model,
                task_working_dir,
                device=device,
                continue_prediction=continue_prediction,
                disable_tta=disable_tta,
                tile_step_size=tile_step_size,
            )
            all_task_results.append((sub_model_spec, result))

        if progress_callback is not None:
            progress_callback(1.0, "Merging predictions")

        merged_prediction_dir = working_dir / "merged_predictions"
        merged_prediction_dir.mkdir(parents=True, exist_ok=True)

        merged_outputs: list[PredictionOutput] = []
        first_result = all_task_results[0][1]

        for output_idx, first_output in enumerate(first_result.outputs):
            case_id = first_output.case_id
            reference_image = cast(nib.Nifti1Image, nib.load(str(first_output.prediction_path)))
            merged = np.zeros(reference_image.shape[:3], dtype=np.int16)

            for sub_spec, task_result in all_task_results:
                task_output = task_result.outputs[output_idx]
                if not task_output.prediction_path.exists():
                    raise SegmentationDriverError(
                        f"Expected prediction file missing before merge: "
                        f"{task_output.prediction_path}"
                    )
                task_image = cast(
                    nib.Nifti1Image,
                    nib.load(str(task_output.prediction_path)),
                )
                task_data = np.asarray(task_image.dataobj, dtype=np.int16)
                for source_label, unified_label in sub_spec.label_cherry_pick.items():
                    voxels = task_data == source_label
                    if np.any(voxels):
                        merged[voxels] = unified_label

            merged_path = merged_prediction_dir / f"{case_id}.nii.gz"
            nib.save(
                nib.Nifti1Image(merged, reference_image.affine, reference_image.header),
                str(merged_path),
            )
            merged_outputs.append(
                PredictionOutput(
                    case_id=case_id,
                    source_path=first_output.source_path,
                    staged_input_path=first_output.staged_input_path,
                    prediction_path=merged_path,
                    diagnostics_path=None,
                )
            )

        finished_at_utc = utc_now()
        task_names = [spec.dataset_name for spec, _ in all_task_results]
        return PredictionBatchResult(
            working_dir=working_dir,
            staged_input_dir=first_result.staged_input_dir,
            prediction_dir=merged_prediction_dir,
            command=("cads-composite", *task_names),
            log_path=None,
            device=device,
            outputs=tuple(merged_outputs),
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            stdout=f"Merged {len(all_task_results)} CADS task models",
            stderr="",
        )


def _build_sub_runtime_model(
    *,
    parent: SegmentationRuntimeModel,
    spec: CompositeSubModelSpec,
) -> SegmentationRuntimeModel:
    """Build a single-task SegmentationRuntimeModel for the inner nnU-Net driver."""
    inference_spec = SegmentationBundleInferenceSpec(
        dataset_id=int(spec.dataset_name.split("_")[0].removeprefix("Dataset")),
        dataset_name=spec.dataset_name.split("_", 1)[1] if "_" in spec.dataset_name else spec.dataset_name,
        trainer_name=spec.trainer_name,
        plan_name=spec.plan_name,
        configuration=spec.configuration,
    )
    trainer_dir_name = f"{spec.trainer_name}__{spec.plan_name}__{spec.configuration}"
    checkpoint_path = (
        parent.runtime_results_root
        / spec.dataset_name
        / trainer_dir_name
        / f"fold_{spec.fold}"
        / spec.checkpoint_name
    )
    checkpoint = SegmentationBundleCheckpoint(
        checkpoint_id=f"fold-{spec.fold}:{spec.checkpoint_name.removesuffix('.pth')}",
        fold=spec.fold,
        checkpoint_name=spec.checkpoint_name,
        relative_path=str(checkpoint_path.relative_to(parent.runtime_results_root.parent)),
    )
    identity_mapping = {str(i): i for i in spec.label_cherry_pick}
    return SegmentationRuntimeModel(
        model_id=f"{parent.model_id}:{spec.dataset_name}",
        display_name=f"{parent.display_name} ({spec.dataset_name})",
        family=parent.family,
        driver_id=DRIVER_ID_NNUNETV2,
        environment_id=parent.environment_id,
        modality=parent.modality,
        inference_spec=inference_spec,
        checkpoint=checkpoint,
        runtime_results_root=parent.runtime_results_root,
        checkpoint_path=checkpoint_path,
        label_mapping=identity_mapping,
        provenance=parent.provenance,
    )


def resolve_segmentation_driver(
    driver_id: str,
    *,
    performance_policy: PerformancePolicy | None = None,
) -> SegmentationModelDriver:
    policy = performance_policy or active_performance_policy()
    if driver_id == DRIVER_ID_NNUNETV2:
        return NNUNetV2SegmentationDriver(
            preprocessing_workers=policy.nnunet_preprocess_workers,
            export_workers=policy.nnunet_export_workers,
        )
    if driver_id == DRIVER_ID_CADS_COMPOSITE:
        return CADSCompositeSegmentationDriver(
            preprocessing_workers=policy.nnunet_preprocess_workers,
            export_workers=policy.nnunet_export_workers,
        )
    raise SegmentationDriverError(f"Unsupported segmentation driver: {driver_id}")
