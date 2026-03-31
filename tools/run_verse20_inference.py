from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from spinelab.segmentation import (
    NNUNetV2SegmentationDriver,
    build_legacy_nnunet_runtime_model,
    resolve_segmentation_driver,
)

DEFAULT_OUTPUT_ROOT = Path(r"D:\dev\spinelab_data\raw_test_data\outputs")
DEFAULT_RAW_TEST_DATA_ROOT = Path(r"D:\dev\spinelab_data\raw_test_data")
DEFAULT_VERSE_TEST_ROOT = Path(r"E:\data\verse_data\03_test\rawdata")
DEFAULT_RESULTS_ROOT = Path(r"D:\dev\spinelab_data\nnunet\results")
DEFAULT_DATASET_ID = 321
DEFAULT_DATASET_NAME = "VERSE20Vertebrae"
DEFAULT_PLAN_NAME = "nnUNetResEncL_24G"
DEFAULT_TRAINER_NAME = "nnUNetTrainer"
DEFAULT_CONFIGURATION = "3d_fullres"
DEFAULT_FOLD = "0"
DEFAULT_CHECKPOINT = "checkpoint_final.pth"
DEFAULT_RANDOM_SEED = 20260326


@dataclass(frozen=True, slots=True)
class SourceCase:
    case_id: str
    source_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage CT NIfTI inputs for nnU-Net v2 prediction and run VERSe20-style "
            "vertebra inference into the SpineLab raw_test_data outputs tree."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("raw-test-data", "verse03-random", "explicit"),
        required=True,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Base output folder. Job folders are created underneath this root.",
    )
    parser.add_argument(
        "--raw-test-data-root",
        type=Path,
        default=DEFAULT_RAW_TEST_DATA_ROOT,
    )
    parser.add_argument(
        "--verse-test-root",
        type=Path,
        default=DEFAULT_VERSE_TEST_ROOT,
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        nargs="*",
        help="Explicit input NIfTI paths. Required when --mode explicit is used.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="Number of random VERSe 03_test scans to select for --mode verse03-random.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_RANDOM_SEED,
        help="Random seed for --mode verse03-random.",
    )
    parser.add_argument(
        "--job-name",
        help="Optional stable output folder name. Defaults to a timestamped job label.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=DEFAULT_RESULTS_ROOT,
        help="nnUNet_results root containing Dataset321_VERSE20Vertebrae/...",
    )
    parser.add_argument("--dataset-id", type=int, default=DEFAULT_DATASET_ID)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--plan-name", default=DEFAULT_PLAN_NAME)
    parser.add_argument("--trainer-name", default=DEFAULT_TRAINER_NAME)
    parser.add_argument("--configuration", default=DEFAULT_CONFIGURATION)
    parser.add_argument("--fold", default=DEFAULT_FOLD)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="Prediction device. Auto prefers CUDA when available.",
    )
    parser.add_argument(
        "--npp",
        type=int,
        default=2,
        help="nnU-Net preprocessing worker count.",
    )
    parser.add_argument(
        "--nps",
        type=int,
        default=2,
        help=(
            "Retained for compatibility with the shared driver. The Windows "
            "sidecar exports predictions in-process."
        ),
    )
    parser.add_argument(
        "--disable-tta",
        action="store_true",
        help="Disable test-time mirroring augmentation.",
    )
    parser.add_argument(
        "--continue-prediction",
        action="store_true",
        help="Resume a previously interrupted output folder instead of overwriting it.",
    )
    return parser.parse_args(argv)


def utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def auto_device() -> str:
    try:
        import torch
    except Exception:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def dataset_dir_name(dataset_id: int, dataset_name: str) -> str:
    return f"Dataset{dataset_id:03d}_{dataset_name}"


def collect_raw_test_data_cases(root: Path) -> list[SourceCase]:
    if not root.exists():
        raise FileNotFoundError(f"raw_test_data root does not exist: {root}")
    cases: list[SourceCase] = []
    for path in sorted(root.glob("*.nii.gz")):
        cases.append(SourceCase(case_id=path.name.removesuffix(".nii.gz"), source_path=path))
    if not cases:
        raise FileNotFoundError(f"No .nii.gz scans found under {root}")
    return cases


def collect_verse_random_cases(root: Path, sample_size: int, seed: int) -> list[SourceCase]:
    if not root.exists():
        raise FileNotFoundError(f"VERSe 03_test rawdata root does not exist: {root}")
    candidates: list[Path] = sorted(root.glob(r"sub-*\*_ct.nii.gz"))
    if not candidates:
        raise FileNotFoundError(f"No VERSe 03_test CT scans found under {root}")
    if sample_size < 1:
        raise ValueError("--sample-size must be at least 1.")
    if sample_size > len(candidates):
        raise ValueError(
            f"Requested sample size {sample_size}, but only found {len(candidates)} VERSe scans."
        )
    rng = random.Random(seed)
    selected = sorted(rng.sample(candidates, sample_size), key=lambda path: path.name)
    return [
        SourceCase(
            case_id=path.name.removesuffix(".nii.gz"),
            source_path=path,
        )
        for path in selected
    ]


def collect_explicit_cases(paths: list[Path] | None) -> list[SourceCase]:
    if not paths:
        raise ValueError("--inputs is required when --mode explicit is used.")
    cases: list[SourceCase] = []
    for raw_path in paths:
        path = raw_path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Explicit input does not exist: {path}")
        if path.suffixes[-2:] != [".nii", ".gz"]:
            raise ValueError(f"Expected a .nii.gz file, got: {path}")
        cases.append(SourceCase(case_id=path.name.removesuffix(".nii.gz"), source_path=path))
    return cases


def select_cases(args: argparse.Namespace) -> list[SourceCase]:
    if args.mode == "raw-test-data":
        return collect_raw_test_data_cases(args.raw_test_data_root.resolve())
    if args.mode == "verse03-random":
        return collect_verse_random_cases(
            args.verse_test_root.resolve(),
            sample_size=args.sample_size,
            seed=args.seed,
        )
    return collect_explicit_cases(args.inputs)


def write_manifest(
    *,
    manifest_path: Path,
    args: argparse.Namespace,
    job_dir: Path,
    staged_input_dir: Path,
    prediction_dir: Path,
    cases: list[SourceCase],
    command: list[str],
    device: str,
    runtime_model,
    sidecar_log_path: Path | None,
) -> None:
    payload = {
        "created_at_utc": utc_timestamp(),
        "mode": args.mode,
        "job_dir": str(job_dir),
        "staged_input_dir": str(staged_input_dir),
        "prediction_dir": str(prediction_dir),
        "sidecar_log_path": str(sidecar_log_path) if sidecar_log_path is not None else "",
        "model": {
            "driver_id": runtime_model.driver_id,
            "environment_id": runtime_model.environment_id,
            "family": runtime_model.family,
            "model_id": runtime_model.model_id,
            "display_name": runtime_model.display_name,
            "results_root": str(runtime_model.runtime_results_root),
            "dataset_id": runtime_model.inference_spec.dataset_id,
            "dataset_name": runtime_model.inference_spec.dataset_name,
            "plan_name": runtime_model.inference_spec.plan_name,
            "trainer_name": runtime_model.inference_spec.trainer_name,
            "configuration": runtime_model.inference_spec.configuration,
            "fold": runtime_model.checkpoint.fold,
            "checkpoint": runtime_model.checkpoint.checkpoint_name,
            "checkpoint_id": runtime_model.checkpoint.checkpoint_id,
            "checkpoint_path": str(runtime_model.checkpoint_path),
            "device": device,
        },
        "sampling": {
            "sample_size": args.sample_size if args.mode == "verse03-random" else None,
            "seed": args.seed if args.mode == "verse03-random" else None,
        },
        "inputs": [asdict(case) | {"source_path": str(case.source_path)} for case in cases],
        "nnunet_command": command,
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_root = args.output_root.resolve()
    results_root = args.results_root.resolve()
    runtime_model = build_legacy_nnunet_runtime_model(
        results_root=results_root,
        dataset_id=args.dataset_id,
        dataset_name=args.dataset_name,
        trainer_name=args.trainer_name,
        plan_name=args.plan_name,
        configuration=args.configuration,
        fold=args.fold,
        checkpoint_name=args.checkpoint,
    )
    cases = select_cases(args)
    device = auto_device() if args.device == "auto" else args.device

    if args.job_name:
        job_name = args.job_name
    elif args.mode == "raw-test-data":
        job_name = "raw_test_data_all"
    elif args.mode == "verse03-random":
        job_name = f"verse03_random{len(cases)}_{args.seed}_{utc_timestamp()}"
    else:
        job_name = f"explicit_{len(cases)}_{utc_timestamp()}"

    job_dir = output_root / job_name
    if job_dir.exists() and not args.continue_prediction:
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running nnU-Net prediction for {len(cases)} scan(s).")
    print(f"Job directory: {job_dir}")
    print(f"Using checkpoint: {runtime_model.checkpoint_path}")
    print(f"Device: {device}")

    if runtime_model.driver_id == "nnunetv2":
        driver = NNUNetV2SegmentationDriver(
            preprocessing_workers=args.npp,
            export_workers=args.nps,
        )
    else:
        driver = resolve_segmentation_driver(runtime_model.driver_id)
    prediction_result = driver.predict_batch(
        tuple(case.source_path.resolve() for case in cases),
        runtime_model,
        job_dir,
        device=device,
        continue_prediction=args.continue_prediction,
        disable_tta=args.disable_tta,
    )

    manifest_path = job_dir / "run_manifest.json"
    write_manifest(
        manifest_path=manifest_path,
        args=args,
        job_dir=job_dir,
        staged_input_dir=prediction_result.staged_input_dir,
        prediction_dir=prediction_result.prediction_dir,
        cases=cases,
        command=list(prediction_result.command),
        device=device,
        runtime_model=runtime_model,
        sidecar_log_path=prediction_result.log_path,
    )

    print(f"Prediction directory: {prediction_result.prediction_dir}")
    print("Prediction completed successfully.")
    print(f"Manifest written to: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
