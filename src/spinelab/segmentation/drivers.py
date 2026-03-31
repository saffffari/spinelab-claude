from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import nibabel as nib
import numpy as np

from spinelab.models.manifest import utc_now
from spinelab.ontology import STANDARD_LEVEL_IDS, normalize_level_id
from spinelab.segmentation.bundles import SegmentationRuntimeModel
from spinelab.segmentation.process_control import run_tracked_segmentation_subprocess
from spinelab.services.performance import PerformancePolicy, active_performance_policy

DRIVER_ID_NNUNETV2 = "nnunetv2"
DRIVER_ID_TOTALSEGMENTATOR = "totalsegmentator"
DRIVER_ID_SKELLYTOUR = "skellytour"
DEFAULT_NNUNET_CONDA_ENV_NAME = "spinelab-nnunet-verse20-win"
DEFAULT_TOTALSEGMENTATOR_CONDA_ENV_NAME = "totalsegmentator-win"
DEFAULT_SKELLYTOUR_CONDA_ENV_NAME = "skellytour-win"
NNUNET_PREFLIGHT_GUARD_EXIT_CODE = 12
_ENVIRONMENT_ID_TO_CONDA_ENV = {
    "nnunet-verse20-win": DEFAULT_NNUNET_CONDA_ENV_NAME,
    "totalsegmentator-win": DEFAULT_TOTALSEGMENTATOR_CONDA_ENV_NAME,
    "skellytour-win": DEFAULT_SKELLYTOUR_CONDA_ENV_NAME,
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


def _resolve_totalsegmentator_executable() -> str | None:
    candidates = (
        shutil.which("TotalSegmentator"),
        shutil.which("TotalSegmentator.exe"),
        shutil.which("totalsegmentator"),
    )
    for candidate in candidates:
        if candidate:
            return candidate
    return None


def _totalsegmentator_source_label_mapping(
    *,
    environment_id: str,
    task_name: str,
) -> dict[str, int]:
    python_command = _environment_python_command(environment_id)
    if python_command is None:
        raise SegmentationDriverError(
            "Unable to locate the TotalSegmentator runtime environment."
        )
    mapping_script = (
        "import json, sys; "
        "from totalsegmentator.map_to_binary import class_map; "
        "payload = class_map.get(sys.argv[1]); "
        "print(json.dumps(payload if isinstance(payload, dict) else {}))"
    )
    completed = subprocess.run(
        [*python_command, "-c", mapping_script, task_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SegmentationDriverError(
            "Unable to resolve the TotalSegmentator class map from the configured "
            f"runtime.\n{completed.stderr or completed.stdout}"
        )
    try:
        task_map = cast(dict[object, object], json.loads(completed.stdout))
    except Exception as exc:
        raise SegmentationDriverError(
            "TotalSegmentator class-map output could not be decoded."
        ) from exc
    if not isinstance(task_map, dict):
        raise SegmentationDriverError(
            f"TotalSegmentator task {task_name!r} is not available in the installed runtime."
        )
    mapping: dict[str, int] = {}
    for label_value, class_name in task_map.items():
        if not isinstance(class_name, str) or not class_name.startswith("vertebrae_"):
            continue
        level_id = normalize_level_id(class_name.removeprefix("vertebrae_"))
        if level_id is None or level_id not in STANDARD_LEVEL_IDS:
            continue
        try:
            mapping[level_id] = int(str(label_value))
        except (TypeError, ValueError):
            continue
    return mapping


_SKELLYTOUR_HIGH_SOURCE_LABEL_MAPPING = {
    "C1": 36,
    "C2": 37,
    "C3": 38,
    "C4": 39,
    "C5": 40,
    "C6": 41,
    "C7": 42,
    "T1": 43,
    "T2": 44,
    "T3": 45,
    "T4": 46,
    "T5": 47,
    "T6": 48,
    "T7": 49,
    "T8": 50,
    "T9": 51,
    "T10": 52,
    "T11": 53,
    "T12": 54,
    "L1": 55,
    "L2": 56,
    "L3": 57,
    "L4": 58,
    "L5": 59,
}


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


def _resolve_skellytour_prediction_path(
    *,
    output_dir: Path,
    case_id: str,
    model_name: str,
) -> Path | None:
    preferred_candidates = (
        output_dir / f"{case_id}_{model_name}_postprocessed.nii.gz",
        output_dir / f"{case_id}_{model_name}.nii.gz",
    )
    for candidate in preferred_candidates:
        if candidate.exists():
            return candidate
    glob_candidates = sorted(
        output_dir.glob(f"{case_id}_{model_name}*.nii.gz"),
        key=lambda path: path.name.lower(),
    )
    return glob_candidates[0] if glob_candidates else None


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
    ) -> PredictionBatchResult:
        return self.predict_batch(
            (normalized_volume_path,),
            runtime_model,
            working_dir,
            device=device,
            continue_prediction=continue_prediction,
            disable_tta=disable_tta,
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
        command_list.append("--fail_on_oversized_preflight")
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
            if completed.returncode == NNUNET_PREFLIGHT_GUARD_EXIT_CODE:
                raise SegmentationDriverError(
                    "nnU-Net sidecar preflight blocked the case before prediction because "
                    "the estimated full-volume results buffers exceed the configured device "
                    "budget.\nsidecar_log:\n"
                    f"{log_path}\noutput_tail:\n{log_excerpt}"
                )
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


class TotalSegmentatorSegmentationDriver:
    driver_id = DRIVER_ID_TOTALSEGMENTATOR

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
    ) -> PredictionBatchResult:
        return self.predict_batch(
            (normalized_volume_path,),
            runtime_model,
            working_dir,
            device=device,
            continue_prediction=continue_prediction,
            disable_tta=disable_tta,
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
    ) -> PredictionBatchResult:
        del disable_tta
        if runtime_model.driver_id != self.driver_id:
            raise SegmentationDriverError(
                f"Runtime model {runtime_model.model_id} uses driver {runtime_model.driver_id!r}, "
                f"not {self.driver_id!r}."
            )
        command_prefix = _environment_command(
            runtime_model.environment_id,
            executable_names=("TotalSegmentator", "totalsegmentator"),
        )
        if command_prefix is None:
            raise SegmentationDriverError(
                "Unable to resolve the TotalSegmentator runtime command from the "
                "configured environment."
            )
        if not runtime_model.checkpoint_path.exists():
            raise SegmentationDriverError(
                "Resolved TotalSegmentator bundle metadata is missing: "
                f"{runtime_model.checkpoint_path}"
            )
        task_name = (
            runtime_model.provenance.get("task")
            or runtime_model.inference_spec.plan_name
            or "total"
        )
        roi_subset = tuple(
            item.strip()
            for item in runtime_model.provenance.get("roi_subset", "").split(",")
            if item.strip()
        )
        source_level_map = _totalsegmentator_source_label_mapping(
            environment_id=runtime_model.environment_id,
            task_name=task_name,
        )
        if not source_level_map:
            raise SegmentationDriverError(
                f"TotalSegmentator task {task_name!r} does not expose supported vertebra labels."
            )

        staged_input_dir = working_dir / "inputs"
        prediction_dir = working_dir / "predictions"
        if staged_input_dir.exists():
            shutil.rmtree(staged_input_dir)
        if prediction_dir.exists() and not continue_prediction:
            shutil.rmtree(prediction_dir)
        staged_input_dir.mkdir(parents=True, exist_ok=True)
        prediction_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[PredictionOutput] = []
        commands: list[tuple[str, ...]] = []
        log_chunks: list[str] = []
        started_at_utc = utc_now()

        for normalized_volume_path in normalized_volume_paths:
            resolved_input = normalized_volume_path.resolve()
            if not resolved_input.exists():
                raise SegmentationDriverError(
                    f"Normalized input volume is missing: {resolved_input}"
                )
            case_id = resolved_input.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}_0000.nii.gz"
            _copy_file_or_hardlink(resolved_input, staged_input_path)
            raw_prediction_path = prediction_dir / f"{case_id}_raw.nii.gz"
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            log_path = working_dir / f"{case_id}.log"
            command: list[str] = [
                *command_prefix,
                "-i",
                str(staged_input_path),
                "-o",
                str(raw_prediction_path),
                "-ml",
                "-ta",
                task_name,
                "-nr",
                str(self._preprocessing_workers),
                "-ns",
                str(self._export_workers),
                "-d",
                "gpu" if device == "cuda" else device,
                "-q",
            ]
            if roi_subset:
                command.extend(["-rs", *roi_subset])
            completed = run_tracked_segmentation_subprocess(
                command,
                capture_output=True,
                text=True,
                check=False,
                label="totalsegmentator-predict",
            )
            command_tuple = tuple(command)
            commands.append(command_tuple)
            combined_log = (completed.stdout or "").strip()
            if completed.stderr:
                combined_log = (
                    f"{combined_log}\n{completed.stderr.strip()}"
                    if combined_log
                    else completed.stderr.strip()
                )
            log_path.write_text(combined_log, encoding="utf-8", errors="replace")
            log_chunks.append(combined_log)
            if completed.returncode != 0:
                raise SegmentationDriverError(
                    "TotalSegmentator prediction failed with exit code "
                    f"{completed.returncode}.\nlog:\n{log_path}\noutput_tail:\n{combined_log[-32768:]}"
                )
            if not raw_prediction_path.exists():
                raise SegmentationDriverError(
                    f"TotalSegmentator completed without writing {raw_prediction_path}."
                )

            _remap_prediction_labels(
                raw_prediction_path=raw_prediction_path,
                prediction_path=prediction_path,
                runtime_model=runtime_model,
                source_level_map=source_level_map,
                driver_label="TotalSegmentator",
            )
            outputs.append(
                PredictionOutput(
                    case_id=case_id,
                    source_path=resolved_input,
                    staged_input_path=staged_input_path,
                    prediction_path=prediction_path,
                )
            )

        finished_at_utc = utc_now()
        final_command: tuple[str, ...] = commands[-1] if commands else ()
        stdout = "\n\n".join(chunk for chunk in log_chunks if chunk).strip()
        return PredictionBatchResult(
            working_dir=working_dir,
            staged_input_dir=staged_input_dir,
            prediction_dir=prediction_dir,
            command=final_command,
            log_path=(working_dir / f"{outputs[-1].case_id}.log") if outputs else None,
            device=device,
            outputs=tuple(outputs),
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            stdout=stdout,
            stderr="",
        )


class SkellyTourSegmentationDriver:
    driver_id = DRIVER_ID_SKELLYTOUR

    def __init__(self, *, preprocessing_workers: int = 6) -> None:
        self._preprocessing_workers = preprocessing_workers

    def predict(
        self,
        normalized_volume_path: Path,
        runtime_model: SegmentationRuntimeModel,
        working_dir: Path,
        *,
        device: str,
        continue_prediction: bool = False,
        disable_tta: bool = False,
    ) -> PredictionBatchResult:
        return self.predict_batch(
            (normalized_volume_path,),
            runtime_model,
            working_dir,
            device=device,
            continue_prediction=continue_prediction,
            disable_tta=disable_tta,
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
    ) -> PredictionBatchResult:
        del disable_tta
        if runtime_model.driver_id != self.driver_id:
            raise SegmentationDriverError(
                f"Runtime model {runtime_model.model_id} uses driver {runtime_model.driver_id!r}, "
                f"not {self.driver_id!r}."
            )
        command_prefix = _environment_command(
            runtime_model.environment_id,
            executable_names=("skellytour",),
        )
        if command_prefix is None:
            raise SegmentationDriverError(
                "Unable to resolve the SkellyTour runtime command from the "
                "configured environment."
            )
        if not runtime_model.checkpoint_path.exists():
            raise SegmentationDriverError(
                "Resolved SkellyTour bundle metadata is missing: "
                f"{runtime_model.checkpoint_path}"
            )
        model_name = (
            runtime_model.provenance.get("model")
            or runtime_model.inference_spec.plan_name
            or "high"
        ).strip()
        if model_name != "high":
            raise SegmentationDriverError(
                "Only the SkellyTour high-label model is supported for canonical "
                "vertebra remapping."
            )

        source_level_map = {
            level_id: source_label
            for level_id, source_label in _SKELLYTOUR_HIGH_SOURCE_LABEL_MAPPING.items()
            if level_id in STANDARD_LEVEL_IDS
        }

        staged_input_dir = working_dir / "inputs"
        prediction_dir = working_dir / "predictions"
        if staged_input_dir.exists():
            shutil.rmtree(staged_input_dir)
        if prediction_dir.exists() and not continue_prediction:
            shutil.rmtree(prediction_dir)
        staged_input_dir.mkdir(parents=True, exist_ok=True)
        prediction_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[PredictionOutput] = []
        commands: list[tuple[str, ...]] = []
        log_chunks: list[str] = []
        started_at_utc = utc_now()

        for normalized_volume_path in normalized_volume_paths:
            resolved_input = normalized_volume_path.resolve()
            if not resolved_input.exists():
                raise SegmentationDriverError(
                    f"Normalized input volume is missing: {resolved_input}"
                )
            case_id = resolved_input.name.removesuffix(".nii.gz").removesuffix(".nii")
            staged_input_path = staged_input_dir / f"{case_id}.nii.gz"
            _copy_file_or_hardlink(resolved_input, staged_input_path)
            case_output_dir = prediction_dir / case_id
            if case_output_dir.exists() and not continue_prediction:
                shutil.rmtree(case_output_dir)
            case_output_dir.mkdir(parents=True, exist_ok=True)
            prediction_path = prediction_dir / f"{case_id}.nii.gz"
            log_path = working_dir / f"{case_id}.log"
            command = [
                *command_prefix,
                "-i",
                str(staged_input_path),
                "-o",
                str(case_output_dir),
                "-m",
                model_name,
                "-c",
                str(self._preprocessing_workers),
                "-d",
                "gpu" if device == "cuda" else device,
                "--overwrite",
            ]
            completed = run_tracked_segmentation_subprocess(
                command,
                capture_output=True,
                text=True,
                check=False,
                label="skellytour-predict",
            )
            command_tuple = tuple(command)
            commands.append(command_tuple)
            combined_log = (completed.stdout or "").strip()
            if completed.stderr:
                combined_log = (
                    f"{combined_log}\n{completed.stderr.strip()}"
                    if combined_log
                    else completed.stderr.strip()
                )
            log_path.write_text(combined_log, encoding="utf-8", errors="replace")
            log_chunks.append(combined_log)
            if completed.returncode != 0:
                raise SegmentationDriverError(
                    "SkellyTour prediction failed with exit code "
                    f"{completed.returncode}.\nlog:\n{log_path}\noutput_tail:\n{combined_log[-32768:]}"
                )
            raw_prediction_path = _resolve_skellytour_prediction_path(
                output_dir=case_output_dir,
                case_id=case_id,
                model_name=model_name,
            )
            if raw_prediction_path is None:
                raise SegmentationDriverError(
                    "SkellyTour completed without writing an expected prediction volume "
                    f"for case {case_id!r} in {case_output_dir}."
                )
            _remap_prediction_labels(
                raw_prediction_path=raw_prediction_path,
                prediction_path=prediction_path,
                runtime_model=runtime_model,
                source_level_map=source_level_map,
                driver_label="SkellyTour",
            )
            outputs.append(
                PredictionOutput(
                    case_id=case_id,
                    source_path=resolved_input,
                    staged_input_path=staged_input_path,
                    prediction_path=prediction_path,
                )
            )

        finished_at_utc = utc_now()
        final_command: tuple[str, ...] = commands[-1] if commands else ()
        stdout = "\n\n".join(chunk for chunk in log_chunks if chunk).strip()
        return PredictionBatchResult(
            working_dir=working_dir,
            staged_input_dir=staged_input_dir,
            prediction_dir=prediction_dir,
            command=final_command,
            log_path=(working_dir / f"{outputs[-1].case_id}.log") if outputs else None,
            device=device,
            outputs=tuple(outputs),
            started_at_utc=started_at_utc,
            finished_at_utc=finished_at_utc,
            stdout=stdout,
            stderr="",
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
    if driver_id == DRIVER_ID_TOTALSEGMENTATOR:
        return TotalSegmentatorSegmentationDriver(
            preprocessing_workers=policy.nnunet_preprocess_workers,
            export_workers=policy.nnunet_export_workers,
        )
    if driver_id == DRIVER_ID_SKELLYTOUR:
        return SkellyTourSegmentationDriver(
            preprocessing_workers=policy.cpu_heavy_workers,
        )
    raise SegmentationDriverError(f"Unsupported segmentation driver: {driver_id}")
